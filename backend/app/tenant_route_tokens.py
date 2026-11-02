"""Authenticated tenant hints for NEW opaque credentials (staged, not enabled).

This module only discovers which tenant database pool may be consulted. The
returned hint is NOT user authentication or permission to access patient data.
Refresh, portal and consent handlers MUST still verify the SHA-256 of the full
token in the tenant database, expiration, revocation and replay rules.

Legacy bearer tokens intentionally do not produce routing hints; a separately
audited transition/resolver is required before changing live API dependencies.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

_PREFIX = "mt1"
_DOMAIN = b"medtour:tenant-token-routing:v1\x00"
_KID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,16}\Z")
_RANDOM_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_TAG_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_MAX_TTL_SECONDS = MappingProxyType({
    "refresh": 7 * 24 * 60 * 60,
    "mfa": 5 * 60,
    "portal": 2 * 60 * 60,
    "consent": 30 * 60,
})


@dataclass(frozen=True)
class VerifiedTenantHint:
    tenant_id: str
    purpose: str
    expires_at: int
    key_id: str


def _tenant_id(value: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("Expected a canonical tenant UUID")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Expected a canonical tenant UUID") from exc
    if normalized != value:
        raise ValueError("Expected a canonical lowercase tenant UUID")
    return normalized


def _timestamp(value: int | None) -> int:
    if value is None:
        return int(time.time())
    if type(value) is not int or value < 0:
        raise ValueError("Invalid Unix timestamp")
    return value


def _signature(key: bytes, payload: str) -> str:
    tag = hmac.new(key, _DOMAIN + payload.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(tag).rstrip(b"=").decode("ascii")


class TenantRouteKeyring:
    """Explicit versioned secrets with old-key verification for safe rotation.

    Secrets MUST come from a secret manager, be random >=32 bytes, and be
    independent of JWT_SECRET. This component never reads untrusted tenant
    identifiers or secrets directly from HTTP requests or the database.
    """

    def __init__(self, keys: Mapping[str, bytes], active_key_id: str):
        if not isinstance(active_key_id, str) or not _KID_PATTERN.fullmatch(active_key_id):
            raise ValueError("Invalid active key ID")
        if not isinstance(keys, Mapping) or not keys:
            raise ValueError("At least one route signing key is required")
        validated = {}
        for kid, value in keys.items():
            if not isinstance(kid, str) or not _KID_PATTERN.fullmatch(kid):
                raise ValueError("Invalid route signing key ID")
            if not isinstance(value, bytes) or len(value) < 32:
                raise ValueError("Route signing keys must have at least 32 bytes")
            validated[kid] = value
        if active_key_id not in validated:
            raise ValueError("Active key not found")
        self._keys = MappingProxyType(validated)
        self._active = active_key_id

    def issue(
        self, *, purpose: str, tenant_id: str, ttl_seconds: int,
        now: int | None = None,
    ) -> str:
        if purpose not in _MAX_TTL_SECONDS:
            raise ValueError("Unknown token purpose")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= _MAX_TTL_SECONDS[purpose]:
            raise ValueError("Token TTL exceeds its security policy")
        canonical = _tenant_id(tenant_id)
        expires_at = _timestamp(now) + ttl_seconds
        random_part = secrets.token_urlsafe(32)
        # Never derive the nonce from a patient/user ID or other private data.
        payload = f"{_PREFIX}.{self._active}.{purpose}.{canonical}.{expires_at}.{random_part}"
        token = f"{payload}.{_signature(self._keys[self._active], payload)}"
        if len(token) > 200:
            raise RuntimeError("Routing token exceeded API field size limit")
        return token

    def verify(
        self, token: str, *, expected_purpose: str,
        now: int | None = None,
    ) -> VerifiedTenantHint | None:
        """Return a hint ONLY after constant-time MAC verification.

        Invalid, expired, legacy and cross-purpose tokens all return None.
        The underlying database must validate the full bearer credential.
        """
        if expected_purpose not in _MAX_TTL_SECONDS:
            raise ValueError("Unknown expected token purpose")
        checked_at = _timestamp(now)
        if not isinstance(token, str) or not 90 <= len(token) <= 200 or not token.isascii():
            return None
        parts = token.split(".")
        if len(parts) != 7:
            return None
        version, kid, purpose, tenant, expiration, nonce, supplied_tag = parts
        if (
            version != _PREFIX or purpose != expected_purpose or
            not _KID_PATTERN.fullmatch(kid) or
            not _RANDOM_PATTERN.fullmatch(nonce) or
            not _TAG_PATTERN.fullmatch(supplied_tag) or
            not expiration.isascii() or not expiration.isdecimal() or
            len(expiration) > 11 or expiration.startswith("0")
        ):
            return None
        key = self._keys.get(kid)
        if key is None:
            return None
        try:
            normalized_tenant = _tenant_id(tenant)
        except ValueError:
            return None
        payload = ".".join(parts[:-1])
        calculated_tag = _signature(key, payload)
        if not hmac.compare_digest(calculated_tag, supplied_tag):
            return None
        expiration_time = int(expiration)
        if not checked_at < expiration_time <= checked_at + _MAX_TTL_SECONDS[purpose]:
            return None
        return VerifiedTenantHint(
            tenant_id=normalized_tenant, purpose=purpose,
            expires_at=expiration_time, key_id=kid,
        )


def token_sha256(raw: str) -> str:
    """Hash the complete credential for storage in the existing token_hash column."""
    if not isinstance(raw, str):
        raise ValueError("Credential must be a string")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
