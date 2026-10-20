"""Stage 19.17: synthetic, deterministic token-to-tenant routing checks.

Cryptographic hints are ONLY the pre-database routing signal; the actual
refresh/portal/consent database credential must still be checked for its hash,
tenant, expiry, replay and revocation state under the correct tenant DB role.
"""
import hashlib
import secrets
from uuid import uuid4

import pytest

from app.tenant_route_tokens import (
    TenantRouteKeyring,
    VerifiedTenantHint,
    token_sha256,
)

NOW = 1_800_000_000
TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"
KEY_ONE = bytes(range(32))
KEY_TWO = bytes(range(32, 64))


@pytest.fixture
def keyring():
    return TenantRouteKeyring({"v1": KEY_ONE}, active_key_id="v1")


@pytest.mark.parametrize("purpose,seconds", [
    ("refresh", 7 * 86400),
    ("portal", 2 * 3600),
    ("consent", 30 * 60),
])
def test_signed_hint_round_trip_preserves_tenant_and_purpose(keyring, purpose, seconds):
    value = keyring.issue(purpose=purpose, tenant_id=TENANT_A, ttl_seconds=seconds, now=NOW)
    assert 90 <= len(value) <= 200
    assert value.count(".") == 6
    parsed = keyring.verify(value, expected_purpose=purpose, now=NOW)
    assert parsed == VerifiedTenantHint(TENANT_A, purpose, NOW + seconds, "v1")
    assert keyring.verify(value, expected_purpose=purpose, now=NOW + seconds) is None


def test_two_tenants_get_independent_hints(keyring):
    a = keyring.issue(purpose="refresh", tenant_id=TENANT_A, ttl_seconds=600, now=NOW)
    b = keyring.issue(purpose="refresh", tenant_id=TENANT_B, ttl_seconds=600, now=NOW)
    assert a != b
    assert keyring.verify(a, expected_purpose="refresh", now=NOW).tenant_id == TENANT_A
    assert keyring.verify(b, expected_purpose="refresh", now=NOW).tenant_id == TENANT_B


def test_random_nonce_prevents_duplicate_tokens(keyring):
    a = keyring.issue(purpose="portal", tenant_id=TENANT_A, ttl_seconds=300, now=NOW)
    b = keyring.issue(purpose="portal", tenant_id=TENANT_A, ttl_seconds=300, now=NOW)
    assert a != b


@pytest.mark.parametrize("field,replacement", [
    (0, "mt2"),
    (1, "evil"),
    (2, "portal"),
    (3, TENANT_B),
    (4, str(NOW + 100)),
    (5, "A" * 43),
    (6, "B" * 43),
])
def test_forged_fields_are_rejected(keyring, field, replacement):
    raw = keyring.issue(purpose="refresh", tenant_id=TENANT_A, ttl_seconds=300, now=NOW)
    fields = raw.split(".")
    fields[field] = replacement
    assert keyring.verify(".".join(fields), expected_purpose="refresh", now=NOW) is None


def test_cross_purpose_use_is_rejected(keyring):
    raw = keyring.issue(purpose="portal", tenant_id=TENANT_A, ttl_seconds=3600, now=NOW)
    assert keyring.verify(raw, expected_purpose="refresh", now=NOW) is None
    assert keyring.verify(raw, expected_purpose="consent", now=NOW) is None


def test_random_legacy_token_has_no_implicit_routing(keyring):
    # Existing stored opaque tokens remain valid for the current, unmodified
    # application endpoints; they cannot be routed by the new cryptographic parser.
    legacy = secrets.token_urlsafe(48)
    assert keyring.verify(legacy, expected_purpose="refresh", now=NOW) is None
    assert keyring.verify("mt1.v1.portal.legacy", expected_purpose="portal", now=NOW) is None


@pytest.mark.parametrize("input_value", ["", "x" * 201, "é" * 125, "a.b.c.d.e.f.g"])
def test_malformed_tokens_have_no_routing_hint(keyring, input_value):
    assert keyring.verify(input_value, expected_purpose="refresh", now=NOW) is None


def test_key_rotation_preserves_old_credentials_until_old_key_retired():
    before = TenantRouteKeyring({"v1": KEY_ONE}, active_key_id="v1")
    old = before.issue(purpose="refresh", tenant_id=TENANT_A, ttl_seconds=900, now=NOW)
    rotated = TenantRouteKeyring({"v1": KEY_ONE, "v2": KEY_TWO}, active_key_id="v2")
    fresh = rotated.issue(purpose="refresh", tenant_id=TENANT_B, ttl_seconds=900, now=NOW)
    assert rotated.verify(old, expected_purpose="refresh", now=NOW).key_id == "v1"
    assert rotated.verify(fresh, expected_purpose="refresh", now=NOW).key_id == "v2"
    retired = TenantRouteKeyring({"v2": KEY_TWO}, active_key_id="v2")
    assert retired.verify(old, expected_purpose="refresh", now=NOW) is None
    assert retired.verify(fresh, expected_purpose="refresh", now=NOW).tenant_id == TENANT_B


def test_wrong_signing_key_cannot_validate_tenant_hint(keyring):
    a = keyring.issue(purpose="refresh", tenant_id=TENANT_A, ttl_seconds=900, now=NOW)
    wrong = TenantRouteKeyring({"v1": KEY_TWO}, active_key_id="v1")
    assert wrong.verify(a, expected_purpose="refresh", now=NOW) is None


@pytest.mark.parametrize("bad_key", [b"", b"short", "not-bytes", 42])
def test_weak_or_non_binary_signing_key_fails_closed(bad_key):
    with pytest.raises(ValueError):
        TenantRouteKeyring({"v1": bad_key}, active_key_id="v1")


def test_unknown_kid_and_missing_active_key_are_rejected():
    with pytest.raises(ValueError):
        TenantRouteKeyring({"v1": KEY_ONE}, active_key_id="v2")
    with pytest.raises(ValueError):
        TenantRouteKeyring({"bad.kid": KEY_ONE}, active_key_id="bad.kid")


@pytest.mark.parametrize("purpose,maximum", [
    ("portal", 7200),
    ("consent", 1800),
    ("refresh", 604800),
])
def test_ttl_upper_bound_enforced(keyring, purpose, maximum):
    with pytest.raises(ValueError):
        keyring.issue(purpose=purpose, tenant_id=TENANT_A, ttl_seconds=maximum + 1, now=NOW)
    with pytest.raises(ValueError):
        keyring.issue(purpose=purpose, tenant_id=TENANT_A, ttl_seconds=0, now=NOW)
    with pytest.raises(ValueError):
        keyring.issue(purpose=purpose, tenant_id=TENANT_A, ttl_seconds=True, now=NOW)


def test_unrecognized_purpose_and_tenant_uuid_are_rejected(keyring):
    with pytest.raises(ValueError):
        keyring.issue(purpose="admin", tenant_id=TENANT_A, ttl_seconds=300, now=NOW)
    with pytest.raises(ValueError):
        keyring.issue(purpose="refresh", tenant_id="not-a-uuid", ttl_seconds=300, now=NOW)
    with pytest.raises(ValueError):
        keyring.issue(purpose="refresh", tenant_id=TENANT_A.upper(), ttl_seconds=300, now=NOW)
    with pytest.raises(ValueError):
        keyring.verify("foo", expected_purpose="admin", now=NOW)


def test_hash_storage_is_compatible_with_existing_sha256_scheme(keyring):
    from app.session_api import hash_token

    raw = keyring.issue(purpose="refresh", tenant_id=TENANT_A, ttl_seconds=300, now=NOW)
    assert token_sha256(raw) == hash_token(raw)
    assert token_sha256(raw) == hashlib.sha256(raw.encode()).hexdigest()
    assert len(token_sha256(raw)) == 64


def test_route_does_not_return_patient_user_or_unhashed_credential(keyring):
    raw = keyring.issue(purpose="consent", tenant_id=TENANT_A, ttl_seconds=60, now=NOW)
    parsed = keyring.verify(raw, expected_purpose="consent", now=NOW)
    assert parsed is not None
    assert "patient" not in parsed.__dataclass_fields__
    assert "user" not in parsed.__dataclass_fields__
    assert "token" not in parsed.__dataclass_fields__
    assert raw not in repr(parsed)
