"""Clone-only FastAPI pre-auth pilot using the verified Epoch->RLS lease chain.

This is an opt-in TESTCLIENT composition root, NOT a deployed ASGI entrypoint.
Never imported by app.main, global get_db or existing WhatsApp processor.

Every DB session acquisition (staff login, refresh rotation or signed Meta
account validation) re-checks the central tenant epoch, then acquires a
short-lived PostgreSQL session through a bounded per-tenant LOGIN pool.
No sessionmaker/engine leaks out of an active lease. On central control-plane
failure, deny new work; never fall back to the global privileged engine.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import contextmanager

from fastapi import FastAPI

from .staged_preauth_http import staged_preauth_router
from .staged_preauth_service import StagedPreAuthService
from .staged_tenant_epoch_control import StagedCoordinatedTenantRegistry
from .staged_tenant_pool_registry import TenantPrincipalConfig
from .tenant_route_tokens import TenantRouteKeyring


class EpochGuardedSessionFactory:
    """Callable session factory API, always enclosed by a fresh verified lease.

    This adapter exists for the older staged transaction interface that uses
    `with factory() as db`. Unlike a raw SQLAlchemy sessionmaker it cannot
    be used to create a DB session without a central epoch check.
    """

    def __init__(self, registry: StagedCoordinatedTenantRegistry, tenant_id: str):
        if not isinstance(registry, StagedCoordinatedTenantRegistry):
            raise ValueError("Expected guarded coordinated registry")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("Expected trusted tenant ID")
        self._registry = registry
        self._tenant_id = tenant_id

    @contextmanager
    def __call__(self):
        with self._registry.acquire_tenant(self._tenant_id) as lease:
            with lease.session() as db:
                yield db


def create_clone_preauth_pilot(
    *, registry: StagedCoordinatedTenantRegistry,
    provisioned: Mapping[str, TenantPrincipalConfig],
    keyring: TenantRouteKeyring,
    meta_app_secret: str,
    whatsapp_approved: bool = False,
) -> FastAPI:
    """Construct a _separate_, synthetic-only app. No production override.

    The provisioned directory must come from controlled server configuration,
    NOT request bodies, query args, headers, shared app user tables or a public
    global tenant list. The already-provisioned registry is checked anew at
    request time, not trusted based only on this constructor.
    """
    if (
        os.getenv("APP_ENV") != "test"
        or os.getenv("DATABASE_URL") != "sqlite://"
        or os.getenv("MEDTOUR_SYNTHETIC_CLONE") != "1"
    ):
        raise RuntimeError("Staged pre-auth pilot is permitted in a synthetic test clone ONLY")
    if not isinstance(registry, StagedCoordinatedTenantRegistry):
        raise ValueError("Tenant epoch registry is required")
    if not isinstance(keyring, TenantRouteKeyring):
        raise ValueError("Tenant HMAC keyring is required")
    if not isinstance(provisioned, Mapping) or not provisioned or len(provisioned) > 16:
        raise ValueError("Trusted pre-provisioned tenant directory required")

    sessions = {}
    slugs = {}
    accounts = {}
    for tid, config in provisioned.items():
        if not isinstance(config, TenantPrincipalConfig) or tid != config.tenant_id:
            raise ValueError("Tenant directory includes unprovisioned or mismatched identity")
        if config.slug in slugs or config.whatsapp_phone_id in accounts:
            raise ValueError("Duplicate tenant alias in trusted server-side directory")
        sessions[tid] = EpochGuardedSessionFactory(registry, tid)
        slugs[config.slug] = tid
        accounts[config.whatsapp_phone_id] = tid

    service = StagedPreAuthService(
        keyring=keyring,
        sessions_by_tenant=sessions,
        tenant_slugs=slugs,
        whatsapp_accounts=accounts,
        whatsapp_app_secret=meta_app_secret,
        whatsapp_approved=whatsapp_approved,
    )
    app = FastAPI(
        title="MedTour Synthetic Pre-auth Migration Pilot",
        description="Synthetic clone-only. No clinical processing or PHI persistence.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(staged_preauth_router(service))
    # Exactly three endpoints; intentionally NO admin, readiness, patient, case,
    # consent, live WhatsApp processor, AI, messaging or documents routes.
    allowed = {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/webhooks/whatsapp"),
    }
    present = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", ())
        if method not in {"HEAD", "OPTIONS"}
    }
    if present != allowed:
        raise RuntimeError("Unsafe route was mounted into synthetic migration pilot")
    return app
