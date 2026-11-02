"""Staged transactional tenant credential operations. NOT wired to live FastAPI.

Security invariants:
- Route by authenticated, purpose-bound MAC BEFORE opening a tenant connection.
- Assert actual PostgreSQL session_user -> protected tenant mapping.
- Match full credential SHA-256 under RLS, verify expiry/revocation.
- Serialize refresh rotation and one-time consent consumption via row locks.
- Never use the current superuser API DATABASE_URL as a fallback.
- Caller must still enforce the privacy notice and authenticate staff requests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .enterprise_models import (
    OutboundMessage,
    PatientConsentChallenge,
    PortalAccess,
    RefreshSession,
    StaffTotp,
    PhysicianAccount,
)
from .models import Audit, Consent, Patient, User
from .tenant_route_tokens import TenantRouteKeyring, token_sha256


@dataclass(frozen=True)
class RotatedRefresh:
    tenant_id: str
    user_id: str
    role: str
    refresh_token: str
    auth_version: int = 0


@dataclass(frozen=True)
class RecordedConsent:
    tenant_id: str
    patient_id: str
    purpose: str
    accepted: bool
    consent_id: str


class StagedTenantCredentialTransactions:
    """Fail-closed, pre-provisioned tenant-role transactions for a test clone.

    The session factories MUST come from trusted provisioning, with unique
    authenticated DB logins per tenant. This class does NOT select/construct
    an Engine from a request-supplied tenant ID or trust a plain session GUC.
    """

    def __init__(
        self,
        *,
        keyring: TenantRouteKeyring,
        sessions_by_tenant: Mapping[str, sessionmaker],
    ) -> None:
        if not isinstance(keyring, TenantRouteKeyring) or not sessions_by_tenant:
            raise ValueError("Required routing keyring and tenant session directory")
        self._keyring = keyring
        self._sessions = dict(sessions_by_tenant)

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        t = value or datetime.now(timezone.utc)
        if t.tzinfo is None:
            raise ValueError("An aware UTC-compatible datetime is required")
        return t.astimezone(timezone.utc)

    @staticmethod
    def _not_expired(expires_at: datetime | None, now: datetime) -> bool:
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > now

    def _resolve(self, token: str, purpose: str, now: datetime):
        hint = self._keyring.verify(
            token, expected_purpose=purpose, now=int(now.timestamp())
        )
        if hint is None:
            return None
        factory = self._sessions.get(hint.tenant_id)
        if factory is None:
            return None
        return hint.tenant_id, factory

    @staticmethod
    def _principal_matches(db, expected_tid: str) -> bool:
        login, mapped = db.execute(
            text("SELECT session_user, medtour_principal_private.tenant_for_login()")
        ).one()
        return bool(login and mapped == expected_tid)

    def rotate_refresh(
        self, token: str, *, now: datetime | None = None
    ) -> RotatedRefresh | None:
        """Atomic rotation; replay invalidates all *currently active* family rows.

        No JWT is issued here. The caller must issue an access JWT only after a
        successful committed rotation, and must not log the raw token.
        """
        checked = self._now(now)
        scoped = self._resolve(token, "refresh", checked)
        if scoped is None:
            return None
        tenant_id, factory = scoped
        try:
            with factory() as db:
                if not self._principal_matches(db, tenant_id):
                    return None
                row = db.scalar(
                    select(RefreshSession)
                    .where(
                        RefreshSession.tenant_id == tenant_id,
                        RefreshSession.refresh_hash == token_sha256(token),
                    )
                    .with_for_update()
                )
                if row is None:
                    return None
                if row.revoked_at is not None:
                    db.execute(
                        update(RefreshSession)
                        .where(
                            RefreshSession.tenant_id == tenant_id,
                            RefreshSession.family_id == row.family_id,
                            RefreshSession.revoked_at.is_(None),
                        )
                        .values(revoked_at=checked)
                    )
                    db.commit()
                    return None
                if not self._not_expired(row.expires_at, checked):
                    return None
                user = db.scalar(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.id == row.user_id,
                        User.active.is_(True),
                    )
                )
                if user is None:return None
                # Staged strict pre-auth has no second-factor handoff yet.
                # Reject MFA identities rather than issuing an MFA-bypassing
                # refresh for a stale or manually injected refresh family.
                if db.scalar(select(StaffTotp.id).where(
                    StaffTotp.tenant_id==tenant_id,
                    StaffTotp.user_id==user.id,StaffTotp.enabled.is_(True))) and not row.mfa_verified:
                    return None
                if user.role=="physician" and not db.scalar(select(PhysicianAccount.id).where(
                    PhysicianAccount.tenant_id==tenant_id,
                    PhysicianAccount.user_id==user.id,PhysicianAccount.active.is_(True))):return None
                # Existing refresh token families issued before MFA enrollment
                # are invalidated on enable. A staged login may not create new
                # families for MFA-enabled users.
                replacement = self._keyring.issue(
                    purpose="refresh", tenant_id=tenant_id,
                    ttl_seconds=7 * 24 * 3600, now=int(checked.timestamp()),
                )
                row.revoked_at = checked
                row.last_rotated_at = checked
                db.add(
                    RefreshSession(
                        tenant_id=tenant_id,
                        user_id=user.id,
                        refresh_hash=token_sha256(replacement),
                        family_id=row.family_id,
                        expires_at=checked + timedelta(days=7),
                        mfa_verified=row.mfa_verified,
                    )
                )
                result = RotatedRefresh(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role=user.role,
                    refresh_token=replacement,
                    auth_version=user.auth_version,
                )
                db.commit()
                return result
        except (SQLAlchemyError, LookupError):
            return None

    def consume_consent(
        self,
        token: str,
        *,
        notice_version: str,
        accepted: bool,
        now: datetime | None = None,
    ) -> RecordedConsent | None:
        """Serialize one-time consent attestation with portal revocation.

        The HTTP boundary must validate the privacy-notice version and patient
        attestation requirements BEFORE invoking this staged service.
        """
        if not isinstance(accepted, bool):
            raise ValueError("accepted must be boolean")
        if (
            not isinstance(notice_version, str)
            or not 1 <= len(notice_version) <= 40
        ):
            raise ValueError("Invalid notice version")
        checked = self._now(now)
        scoped = self._resolve(token, "consent", checked)
        if scoped is None:
            return None
        tenant_id, factory = scoped
        try:
            with factory() as db:
                if not self._principal_matches(db, tenant_id):
                    return None
                row = db.scalar(
                    select(PatientConsentChallenge)
                    .where(
                        PatientConsentChallenge.tenant_id == tenant_id,
                        PatientConsentChallenge.token_hash == token_sha256(token),
                    )
                    .with_for_update()
                )
                if (
                    row is None or row.used_at is not None
                    or not self._not_expired(row.expires_at, checked)
                ):
                    return None
                # The signed hint does not authorize a patient record:
                # recheck the related patient under the same tenant DB role.
                patient_id = row.patient_id
                exists = db.scalar(
                    select(Patient.id).where(
                        Patient.tenant_id == tenant_id,
                        Patient.id == patient_id,
                    )
                )
                if exists is None:
                    return None
                row.used_at = checked
                entry = Consent(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    purpose=row.purpose,
                    accepted=accepted,
                    notice_version=notice_version,
                    source="patient_link",
                )
                db.add(entry)
                db.flush()
                if not accepted:
                    db.execute(
                        update(PortalAccess)
                        .where(
                            PortalAccess.tenant_id == tenant_id,
                            PortalAccess.patient_id == patient_id,
                            PortalAccess.revoked.is_(False),
                        )
                        .values(revoked=True)
                    )
                    db.execute(
                        update(OutboundMessage)
                        .where(
                            OutboundMessage.tenant_id == tenant_id,
                            OutboundMessage.patient_id == patient_id,
                            OutboundMessage.status.in_(["pending_approval", "approved"]),
                        )
                        .values(status="blocked")
                    )
                db.add(
                    Audit(
                        tenant_id=tenant_id,
                        user_id=patient_id,
                        event=(
                            "patient_attested_consent" if accepted
                            else "patient_withdrew_consent"
                        ),
                        entity_type="Consent",
                        entity_id=entry.id,
                    )
                )
                outcome = RecordedConsent(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    purpose=row.purpose,
                    accepted=accepted,
                    consent_id=entry.id,
                )
                db.commit()
                return outcome
        except (SQLAlchemyError, LookupError):
            return None
