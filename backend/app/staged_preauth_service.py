"""Stage 19.21 — fail-closed pre-auth service for isolated PostgreSQL proof.

This module is NOT imported/mounted by app.main; no production flags or
database credentials are changed. It demonstrates login and signed refresh
under tenant-specific PostgreSQL LOGIN principals, and verifies/routs an
official Meta webhook before any PHI-processing handler is invoked.

A trusted, *pre-provisioned* slug -> tenant ID and phone-number-ID -> tenant ID
directory is required; user-provided headers and slugs NEVER provision roles.
For real deployment: implement registry provisioning, secret manager, connection
bounds, legacy-token transition, webhook persistence and complete review.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Mapping
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .enterprise_models import RefreshSession
from .models import User
from .enterprise_models import StaffTotp,PhysicianAccount,StaffMfaChallenge
from .security import password_hash, password_verify, token_for
from .identity_access import encryption_key,open_secret,accepted_step,utc
from .staged_tenant_transactions import StagedTenantCredentialTransactions
from .tenant_route_tokens import TenantRouteKeyring, token_sha256
from .whatsapp import valid_signature


@dataclass(frozen=True)
class LoginResult:
    tenant_id: str
    user_id: str
    role: str
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class MfaPending:
    challenge_token: str
    expires_in: int


@dataclass(frozen=True)
class VerifiedWebhookRoute:
    tenant_id: str
    phone_number_id: str


def _tenant_uuid(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value
    except (AttributeError, ValueError, TypeError):
        return False


class StagedPreAuthService:
    """Standalone staged service. Never gives database superuser fallback."""

    def __init__(
        self, *, keyring: TenantRouteKeyring,
        sessions_by_tenant: Mapping[str, sessionmaker],
        tenant_slugs: Mapping[str, str],
        whatsapp_accounts: Mapping[str, str],
        whatsapp_app_secret: str,
        whatsapp_approved: bool = False,
    ) -> None:
        if not isinstance(keyring, TenantRouteKeyring) or not sessions_by_tenant:
            raise ValueError("Required keyring and provisioned PostgreSQL session directory")
        if any(not _tenant_uuid(tid) for tid in sessions_by_tenant):
            raise ValueError("Invalid tenant session ID")
        if any(
            not isinstance(slug, str) or not 1 <= len(slug) <= 100
            or not _tenant_uuid(tid) or tid not in sessions_by_tenant
            for slug, tid in tenant_slugs.items()
        ):
            raise ValueError("Unprovisioned tenant slug")
        if any(
            not isinstance(phone_id, str) or not 1 <= len(phone_id) <= 128
            or not _tenant_uuid(tid) or tid not in sessions_by_tenant
            for phone_id, tid in whatsapp_accounts.items()
        ):
            raise ValueError("Unprovisioned WhatsApp business account")
        if not isinstance(whatsapp_app_secret, str) or len(whatsapp_app_secret) < 16:
            raise ValueError("Missing WhatsApp signing secret")
        if not isinstance(whatsapp_approved, bool):
            raise ValueError("Approval must be boolean")
        self._keyring = keyring
        self._sessions = dict(sessions_by_tenant)
        self._slugs = dict(tenant_slugs)
        self._accounts = dict(whatsapp_accounts)
        self._wa_secret = whatsapp_app_secret
        self._wa_approved = whatsapp_approved
        self._transactions = StagedTenantCredentialTransactions(
            keyring=keyring, sessions_by_tenant=sessions_by_tenant
        )
        # Always execute a password check for failed username/slug to reduce
        # observable authentication timing differences. This is NOT a rate limit.
        self._dummy_hash = password_hash("staged-unmatched-account-password")

    def _db_role_matches(self, db, tenant_id: str) -> bool:
        login, mapped = db.execute(
            text("SELECT session_user, medtour_principal_private.tenant_for_login()")
        ).one()
        return bool(login and mapped == tenant_id)

    def _check_dummy(self, password: str) -> None:
        if isinstance(password, str) and len(password) <= 1024:
            password_verify(password, self._dummy_hash)

    def login(self, tenant_slug: str, email: str, password: str) -> LoginResult | None:
        """Check supplied slug against server registry and actual role, then staff."""
        if (
            not isinstance(tenant_slug, str)
            or not isinstance(email, str)
            or not isinstance(password, str)
            or len(tenant_slug) > 100 or len(email) > 250
            or len(password) > 1024 or not password
        ):
            return None
        tenant_id = self._slugs.get(tenant_slug)
        if tenant_id is None:
            self._check_dummy(password)
            return None
        factory = self._sessions.get(tenant_id)
        if factory is None:
            return None
        try:
            with factory() as db:
                if not self._db_role_matches(db, tenant_id):
                    return None
                user = db.scalar(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.email == email.lower().strip(),
                        User.active.is_(True),
                    )
                )
                if user is None:
                    self._check_dummy(password)
                    return None
                if not password_verify(password, user.password_hash):
                    return None
                # MFA identities cannot silently fall back to the staged
                # password-only pre-auth implementation. Full MFA cutover
                # requires an independently audited routed challenge flow.
                factor=db.scalar(select(StaffTotp).where(
                    StaffTotp.tenant_id==tenant_id,StaffTotp.user_id==user.id,
                    StaffTotp.enabled.is_(True)))
                if factor:
                    encryption_key() # Never downgrade to password-only login.
                    started=datetime.now(timezone.utc)
                    challenge=self._keyring.issue(
                        purpose="mfa",tenant_id=tenant_id,ttl_seconds=300,
                        now=int(started.timestamp()))
                    db.add(StaffMfaChallenge(tenant_id=tenant_id,user_id=user.id,
                        challenge_hash=token_sha256(challenge),
                        auth_version=user.auth_version,
                        expires_at=started+timedelta(minutes=5),attempts=0))
                    db.commit()
                    return MfaPending(challenge_token=challenge,expires_in=300)
                if user.role=="physician":
                    linked=db.scalar(select(PhysicianAccount.id).where(
                        PhysicianAccount.tenant_id==tenant_id,
                        PhysicianAccount.user_id==user.id,PhysicianAccount.active.is_(True)))
                    if not linked:return None
                now = datetime.now(timezone.utc)
                raw = self._keyring.issue(
                    purpose="refresh", tenant_id=tenant_id,
                    ttl_seconds=7 * 86400, now=int(now.timestamp()),
                )
                db.add(
                    RefreshSession(
                        tenant_id=tenant_id, user_id=user.id,
                        refresh_hash=token_sha256(raw),
                        family_id=str(uuid4()),
                        expires_at=now + timedelta(days=7),
                    )
                )
                user_id, user_role, version = user.id, user.role, user.auth_version
                db.commit()
                signed_jwt = token_for(
                    SimpleNamespace(id=user_id, tenant_id=tenant_id, role=user_role,
                                    auth_version=version)
                )
                return LoginResult(tenant_id, user_id, user_role, signed_jwt, raw)
        except (SQLAlchemyError, LookupError):
            return None

    def verify_mfa(self,challenge_token:str,code:str)->LoginResult|None:
        """Consume an authenticated tenant-bound challenge before issuing tokens.

        This is the ONLY MFA route for the strict test-clone PostgreSQL
        principal gateway. It does not query any shared superuser session.
        """
        moment=datetime.now(timezone.utc)
        hint=self._keyring.verify(challenge_token,expected_purpose="mfa",
            now=int(moment.timestamp()))
        if not hint:return None
        factory=self._sessions.get(hint.tenant_id)
        if not factory:return None
        try:
            with factory() as db:
                if not self._db_role_matches(db,hint.tenant_id):return None
                raw_hash=token_sha256(challenge_token)
                preliminary=db.scalar(select(StaffMfaChallenge).where(
                    StaffMfaChallenge.tenant_id==hint.tenant_id,
                    StaffMfaChallenge.challenge_hash==raw_hash))
                if not preliminary:return None
                user=db.scalar(select(User).where(
                    User.tenant_id==hint.tenant_id,User.id==preliminary.user_id,
                    User.active.is_(True)).with_for_update())
                if not user:return None
                row=db.scalar(select(StaffMfaChallenge).where(
                    StaffMfaChallenge.tenant_id==hint.tenant_id,
                    StaffMfaChallenge.challenge_hash==raw_hash).with_for_update())
                if (row is None or row.user_id!=user.id or row.auth_version!=user.auth_version
                    or row.used_at is not None or row.attempts>=5
                    or utc(row.expires_at)<=moment):
                    return None
                factor=db.scalar(select(StaffTotp).where(
                    StaffTotp.tenant_id==hint.tenant_id,
                    StaffTotp.user_id==user.id,StaffTotp.enabled.is_(True)).with_for_update())
                if not factor:return None
                row.attempts+=1
                step=accepted_step(open_secret(factor),code,factor.last_step)
                if step is None:
                    if row.attempts>=5:row.used_at=moment
                    db.commit()
                    return None
                factor.last_step=step
                row.used_at=moment
                db.execute(update(StaffMfaChallenge).where(
                    StaffMfaChallenge.tenant_id==hint.tenant_id,
                    StaffMfaChallenge.user_id==user.id,
                    StaffMfaChallenge.used_at.is_(None)).values(used_at=moment))
                replacement=self._keyring.issue(purpose="refresh",
                    tenant_id=hint.tenant_id,ttl_seconds=7*86400,
                    now=int(moment.timestamp()))
                db.add(RefreshSession(tenant_id=hint.tenant_id,user_id=user.id,
                    refresh_hash=token_sha256(replacement),
                    family_id=str(uuid4()),expires_at=moment+timedelta(days=7)))
                uid,role,version=user.id,user.role,user.auth_version
                db.commit()
                jwt_access=token_for(SimpleNamespace(
                    id=uid,tenant_id=hint.tenant_id,role=role,auth_version=version))
                return LoginResult(hint.tenant_id,uid,role,jwt_access,replacement)
        except (SQLAlchemyError,LookupError):
            return None

    def refresh(self, credential: str) -> LoginResult | None:
        """Atomic refresh rotation through the already-tested locked transaction."""
        rotated = self._transactions.rotate_refresh(credential)
        if rotated is None:
            return None
        jwt_access = token_for(
            SimpleNamespace(
                id=rotated.user_id,
                tenant_id=rotated.tenant_id,
                role=rotated.role,
                auth_version=rotated.auth_version,
            )
        )
        return LoginResult(
            tenant_id=rotated.tenant_id,
            user_id=rotated.user_id,
            role=rotated.role,
            access_token=jwt_access,
            refresh_token=rotated.refresh_token,
        )

    def verify_webhook_route(
        self, raw: bytes, signature_header: str | None
    ) -> VerifiedWebhookRoute | None:
        """Verify the *raw* Meta signature and configured phone_number_id.

        This is a routing proof only. No patient matching, clinical processing,
        message storage, approval, reply or external network request occurs.
        """
        if (
            not self._wa_approved or not isinstance(raw, bytes)
            or not 0 < len(raw) <= 262144
            or not valid_signature(raw, signature_header, self._wa_secret)
        ):
            return None
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
            return None
        entries = payload.get("entry")
        if not isinstance(entries, list) or not entries or len(entries) > 100:
            return None
        ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            changes = entry.get("changes")
            if not isinstance(changes, list) or not changes or len(changes) > 100:
                return None
            for change in changes:
                if not isinstance(change, dict) or change.get("field") != "messages":
                    return None
                value = change.get("value")
                if not isinstance(value, dict) or not isinstance(value.get("metadata"), dict):
                    return None
                phone_id = value["metadata"].get("phone_number_id")
                if not isinstance(phone_id, str) or phone_id not in self._accounts:
                    return None
                ids.add(phone_id)
        if len(ids) != 1:
            return None  # Fail closed: mixed accounts cannot share a request
        phone_id = next(iter(ids))
        tenant_id = self._accounts[phone_id]
        factory = self._sessions.get(tenant_id)
        if factory is None:
            return None
        try:
            with factory() as db:
                if not self._db_role_matches(db, tenant_id):
                    return None
                return VerifiedWebhookRoute(tenant_id, phone_id)
        except (SQLAlchemyError, LookupError):
            return None
