"""Fast unit checks for staged tenant transactions; no database is contacted."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.staged_tenant_transactions import StagedTenantCredentialTransactions
from app.tenant_route_tokens import TenantRouteKeyring

KEY = bytes(range(32))
TID_A = "11111111-1111-4111-8111-111111111111"
TID_B = "22222222-2222-4222-8222-222222222222"


class MustNotConnect:
    def __call__(self):
        raise AssertionError("Invalid or foreign token opened a database connection")


def make_service():
    keyring = TenantRouteKeyring({"v1": KEY}, "v1")
    return (
        keyring,
        StagedTenantCredentialTransactions(
            keyring=keyring, sessions_by_tenant={TID_A: MustNotConnect()}
        ),
    )


def test_legacy_token_is_not_accepted_or_routed():
    _, service = make_service()
    assert service.rotate_refresh("legacy-refresh-value") is None
    assert service.consume_consent(
        "legacy-consent-value", notice_version="v1", accepted=True
    ) is None


def test_cross_tenant_hint_with_valid_signature_has_no_pool():
    keyring, service = make_service()
    raw = keyring.issue(purpose="refresh", tenant_id=TID_B, ttl_seconds=60)
    assert service.rotate_refresh(raw) is None


def test_wrong_purpose_hint_never_opens_pool():
    keyring, service = make_service()
    refresh = keyring.issue(purpose="refresh", tenant_id=TID_A, ttl_seconds=60)
    consent = keyring.issue(purpose="consent", tenant_id=TID_A, ttl_seconds=60)
    assert service.consume_consent(
        refresh, notice_version="v1", accepted=True
    ) is None
    assert service.rotate_refresh(consent) is None


def test_invalid_tenant_mac_is_rejected_before_db():
    keyring, service = make_service()
    token = keyring.issue(purpose="consent", tenant_id=TID_A, ttl_seconds=60)
    fields = token.split(".")
    fields[3] = TID_B
    assert service.consume_consent(
        ".".join(fields), notice_version="v1", accepted=True
    ) is None


def test_invalid_notice_version_is_rejected_early():
    _, service = make_service()
    with pytest.raises(ValueError):
        service.consume_consent("bad-token", notice_version="", accepted=True)
    with pytest.raises(ValueError):
        service.consume_consent("bad-token", notice_version="v" * 41, accepted=True)
    with pytest.raises(ValueError):
        service.consume_consent("bad-token", notice_version="v1", accepted=1)


def test_naive_datetime_is_rejected_before_any_query():
    _, service = make_service()
    with pytest.raises(ValueError):
        service.rotate_refresh(
            "not-a-token", now=datetime(2026, 10, 20)
        )
    with pytest.raises(ValueError):
        service.consume_consent(
            "not-a-token", notice_version="v1", accepted=True,
            now=datetime(2026, 10, 20)
        )


def test_malformed_keyring_or_empty_directory_fails_early():
    keyring = TenantRouteKeyring({"v1": KEY}, "v1")
    with pytest.raises(ValueError):
        StagedTenantCredentialTransactions(keyring=keyring, sessions_by_tenant={})
    with pytest.raises(ValueError):
        StagedTenantCredentialTransactions(
            keyring="unverified", sessions_by_tenant={TID_A: MustNotConnect()}
        )
