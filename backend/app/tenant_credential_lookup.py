"""Stage 19.18: fail-closed tenant credential lookup with PostgreSQL RLS.

STAGED PROOF ONLY. Nothing imports this from the running FastAPI dependency graph.
No production credential resolution, database migration, or pool lifecycle is enabled.

Signed tenant hints are routing metadata, NOT authorization. Authorization still
requires the full opaque token's SHA-256 to exist as a valid row under the
PostgreSQL LOGIN role mapped to the tenant.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .enterprise_models import (
    PatientConsentChallenge,
    PortalAccess,
    RefreshSession,
)
from .tenant_route_tokens import TenantRouteKeyring, token_sha256

_MODEL_BY_PURPOSE = {
    "refresh": RefreshSession,
    "portal": PortalAccess,
    "consent": PatientConsentChallenge,
}


def _canonical_tenant(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def _valid_expiration(expires_at: datetime, now: datetime) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


class TenantCredentialLookup:
    """A narrow pre-auth lookup using *pre-provisioned*, trusted DB sessions.

    The mapping is supplied server-side, never constructed from a request
    header or unverified token contents. Each entry must be a distinct
    SQLAlchemy sessionmaker bound to its own PostgreSQL tenant LOGIN role.
    A live migration would additionally require bounded pools, managed
    credentials, revocation, Legacy-token transition and trusted bootstrap.
    """

    def __init__(
        self,
        *,
        keyring: TenantRouteKeyring,
        sessions_by_tenant: Mapping[str, sessionmaker],
    ) -> None:
        if not isinstance(keyring, TenantRouteKeyring):
            raise ValueError("Expected an explicit TenantRouteKeyring")
        if not sessions_by_tenant:
            raise ValueError("Tenant session directory must be nonempty")
        if any(not _canonical_tenant(tid) for tid in sessions_by_tenant):
            raise ValueError("Tenant session directory has invalid identifiers")
        self._keyring = keyring
        self._sessions = dict(sessions_by_tenant)

    def lookup(
        self, token: str, *, purpose: str, now: datetime | None = None
    ) -> str | None:
        """Return the matching credential row ID, never patient/user data.

        No query is issued until the routing MAC and intended purpose pass.
        Rejects all unrecognized tenant IDs, DB principals, hashes, expiries,
        revoked refresh/portal and consumed consent links.
        """
        if purpose not in _MODEL_BY_PURPOSE:
            raise ValueError("Unknown credential purpose")
        checked = now or datetime.now(timezone.utc)
        if checked.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        now_utc = checked.astimezone(timezone.utc)
        hint = self._keyring.verify(
            token, expected_purpose=purpose, now=int(now_utc.timestamp())
        )
        if hint is None:
            return None
        factory = self._sessions.get(hint.tenant_id)
        if factory is None:
            return None

        model = _MODEL_BY_PURPOSE[purpose]
        try:
            with factory() as db:
                # SECURITY DEFINER function resolves the *authenticated* login's
                # tenant, independent of any SQL-writable tenant GUC.
                principal, mapped_tenant = db.execute(
                    text(
                        "SELECT session_user, "
                        "medtour_principal_private.tenant_for_login()"
                    )
                ).one()
                if not principal or mapped_tenant != hint.tenant_id:
                    return None

                row = db.scalar(
                    select(model).where(
                        model.tenant_id == hint.tenant_id,
                        model.token_hash == token_sha256(token)
                        if purpose != "refresh"
                        else model.refresh_hash == token_sha256(token),
                    )
                )
                if row is None or not _valid_expiration(row.expires_at, now_utc):
                    return None
                if purpose == "refresh" and row.revoked_at is not None:
                    return None
                if purpose == "portal" and row.revoked:
                    return None
                if purpose == "consent" and row.used_at is not None:
                    return None
                return row.id
        except SQLAlchemyError:
            # Fail closed when the DB/policy/principal is unavailable; never
            # attempt a fallback through a shared privileged connection.
            return None
