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

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .enterprise_models import RefreshSession
from .models import User
from .security import password_hash, password_verify, token_for
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

    def login(self, tenant_slug: str, email: str, password: str, totp_code: str | None = None) -> LoginResult | None:
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
                from .staff_mfa import verify
                if not verify(db,user,totp_code):
                    return None
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
                user_id, user_role = user.id, user.role
                db.commit()
                signed_jwt = token_for(
                    SimpleNamespace(id=user_id, tenant_id=tenant_id, role=user_role),
                    mfa_verified=True
                )
                return LoginResult(tenant_id, user_id, user_role, signed_jwt, raw)
        except (SQLAlchemyError, LookupError):
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
            ),
            mfa_verified=True
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
