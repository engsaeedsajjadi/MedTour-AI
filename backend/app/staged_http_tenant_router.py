"""Test-only HTTP dependency that routes REAL FastAPI requests to tenant DB roles.

Stage 19.20 — deliberately NOT installed in app.main or production get_db.

This dependency may only be installed by a controlled offline TestClient using
pre-provisioned SQLAlchemy sessions. It rejects routes without a safe pre-auth
resolver (login, refresh rotation, WhatsApp and privileged readiness) rather than
falling back to the global database connection.

A MAC-valid tenant hint does not grant access. The existing FastAPI endpoint
must still verify the credential's complete SHA-256, expiry, revocation and
authorization. Every acquired DB session additionally validates its PostgreSQL
authenticated principal against the protected mapping, independent of GUCs.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .security import secret
from .tenant_credential_lookup import TenantCredentialLookup
from .tenant_route_tokens import TenantRouteKeyring

_BEARER = re.compile(r"Bearer ([^\s]{1,4096})\Z")
_PATH_STAFF = re.compile(r"/api/v1/(?:auth/me|auth/logout|patients(?:/.*)?|cases(?:/.*)?|dashboard)\Z")
_PATH_PORTAL = re.compile(r"/api/v1/portal/(?:me|journey|chat)\Z")
_PATH_CONSENT_PREVIEW = "/api/v1/consent-links/preview"
_PATH_CONSENT_RESPONSE = "/api/v1/consent-links/respond"


def _canonical(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value
    except (TypeError, ValueError, AttributeError):
        return False


class StagedHttpTenantRouter:
    """Explicit deny-by-default route table; no privileged DB fallback.

    Only the stated staff and patient/consent route subsets are covered.
    Not a substitute for the general routing layer, pool lifecycle, secrets
    management, legacy token migration or API migration.
    """

    def __init__(
        self,
        *,
        keyring: TenantRouteKeyring,
        sessions_by_tenant: Mapping[str, sessionmaker],
    ):
        if not isinstance(keyring, TenantRouteKeyring) or not sessions_by_tenant:
            raise ValueError("Signing keyring and pre-provisioned pools required")
        if any(not _canonical(tid) for tid in sessions_by_tenant):
            raise ValueError("Invalid trusted tenant directory")
        self._keyring = keyring
        self._sessions = dict(sessions_by_tenant)
        self._credentials = TenantCredentialLookup(
            keyring=keyring, sessions_by_tenant=sessions_by_tenant,
        )

    @staticmethod
    def _unauthorized():
        raise HTTPException(401, "Invalid or expired credential")

    @staticmethod
    def _unsupported():
        raise HTTPException(503, "Tenant-safe route not yet enabled")

    def _staff_tenant(self, request: Request) -> str:
        authorization = request.headers.get("Authorization", "")
        match = _BEARER.fullmatch(authorization)
        if match is None:
            self._unauthorized()
        try:
            claims = jwt.decode(
                match.group(1), secret(), algorithms=["HS256"],
                options={"require": ["exp", "sub", "tid", "jti"]},
            )
        except jwt.PyJWTError:
            self._unauthorized()
        tenant_id = claims.get("tid")
        if (
            not _canonical(tenant_id)
            or not isinstance(claims.get("sub"), str)
            or not isinstance(claims.get("jti"), str)
            or not isinstance(claims.get("role"), str)
        ):
            self._unauthorized()
        return tenant_id

    def _token_tenant(self, raw: Any, purpose: str) -> str:
        row_id = self._credentials.lookup(raw, purpose=purpose)
        if row_id is None:
            self._unauthorized()
        hint = self._keyring.verify(raw, expected_purpose=purpose)
        if hint is None:
            self._unauthorized()
        return hint.tenant_id

    async def request_tenant(self, request: Request) -> str:
        path = request.url.path
        if _PATH_STAFF.fullmatch(path):
            return self._staff_tenant(request)
        if _PATH_PORTAL.fullmatch(path):
            return self._token_tenant(
                request.headers.get("X-Patient-Access"), "portal"
            )
        if path == _PATH_CONSENT_PREVIEW and request.method == "GET":
            # Existing GET endpoint is included for compatibility test only.
            # Token-in-URL is unsafe for PHI production; must migrate to POST.
            return self._token_tenant(request.query_params.get("token"), "consent")
        if path == _PATH_CONSENT_RESPONSE and request.method == "POST":
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                self._unauthorized()
            if not isinstance(body, dict):
                self._unauthorized()
            return self._token_tenant(body.get("token"), "consent")
        # Includes login, refresh (legacy unrouteable tokens), health/ready,
        # WhatsApp webhook, arbitrary endpoints and all newly introduced paths.
        self._unsupported()

    async def get_db(self, request: Request):
        """FastAPI dependency override of app.database.get_db, stage-only."""
        tid = await self.request_tenant(request)
        factory = self._sessions.get(tid)
        if factory is None:
            self._unauthorized()
        try:
            with factory() as db:
                principal, mapped_tid = db.execute(
                    text(
                        "SELECT session_user, "
                        "medtour_principal_private.tenant_for_login()"
                    )
                ).one()
                if not principal or mapped_tid != tid:
                    self._unauthorized()
                yield db
        except SQLAlchemyError:
            # No fallback to the superuser-backed production SessionLocal.
            raise HTTPException(503, "Tenant database unavailable") from None
