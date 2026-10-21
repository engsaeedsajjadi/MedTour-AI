"""Offline contract tests for the separate synthetic-only Epoch/RLS preauth pilot."""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.staged_epoch_preauth_bridge import (
    EpochGuardedSessionFactory, create_clone_preauth_pilot,
)
from app.staged_tenant_epoch_control import EpochState
from app.tenant_route_tokens import TenantRouteKeyring
from test_stage_19_22_tenant_registry import config, TID_A, TID_B
from test_stage_19_23_multiworker_epoch import SharedEpochReader, worker


def setup(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("MEDTOUR_SYNTHETIC_CLONE", "1")
    authority = SharedEpochReader()
    registry, builder = worker(authority)
    trusted = config()
    registry.provision(trusted, generation=1)
    return authority, registry, builder, trusted


def build(registry, trusted):
    return create_clone_preauth_pilot(
        registry=registry,
        provisioned={trusted.tenant_id: trusted},
        keyring=TenantRouteKeyring({"v1": bytes(range(32))}, "v1"),
        meta_app_secret="synthetic-meta-app-secret-not-for-prod",
        whatsapp_approved=True,
    )


def test_pilot_has_exactly_three_preauth_routes_and_no_phi_endpoints(monkeypatch):
    authority, registry, fake, trusted = setup(monkeypatch)
    try:
        app = build(registry, trusted)
        endpoints = {(method, r.path)
                     for r in app.routes
                     for method in getattr(r, "methods", ())
                     if method not in {"HEAD", "OPTIONS"}}
        assert endpoints == {
            ("POST", "/api/v1/auth/login"),
            ("POST", "/api/v1/auth/refresh"),
            ("POST", "/api/v1/webhooks/whatsapp"),
        }
        client = TestClient(app)
        assert client.get("/api/v1/patients").status_code == 404
        assert client.get("/api/v1/cases").status_code == 404
        assert client.get("/api/v1/health/ready").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.post("/api/v1/webhooks/whatsapp",
                           content=b"{}").status_code == 403
    finally:
        registry.close()


def test_pilot_strips_unexpected_framework_routes_before_mount(monkeypatch):
    """Even if framework registers a route first, the pilot exposes only three."""
    from fastapi import FastAPI
    import app.staged_epoch_preauth_bridge as pilot_module

    class FastAPIWithUnexpectedRoute(FastAPI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.add_api_route(
                "/framework-injected-unsafe", lambda: {"unsafe": True},
                methods=["GET"],
            )

    authority, registry, fake, trusted = setup(monkeypatch)
    try:
        monkeypatch.setattr(pilot_module, "FastAPI", FastAPIWithUnexpectedRoute)
        pilot = build(registry, trusted)
        client = TestClient(pilot)
        assert client.get("/framework-injected-unsafe").status_code == 404
        assert len(pilot.routes) == 3
    finally:
        registry.close()


@pytest.mark.parametrize("env_key,env_value", [
    ("APP_ENV", "production"),
    ("DATABASE_URL", "postgresql://db.example.invalid/application"),
    ("MEDTOUR_SYNTHETIC_CLONE", "0"),
])
def test_pilot_cannot_be_mounted_outside_synthetic_env(monkeypatch, env_key, env_value):
    authority, registry, fake, trusted = setup(monkeypatch)
    try:
        monkeypatch.setenv(env_key, env_value)
        with pytest.raises(RuntimeError, match="synthetic test clone ONLY"):
            build(registry, trusted)
    finally:
        registry.close()


def test_bridge_forces_central_epoch_query_for_every_new_session(monkeypatch):
    authority, registry, fake, trusted = setup(monkeypatch)
    factory = EpochGuardedSessionFactory(registry, trusted.tenant_id)
    before = authority.calls
    try:
        with factory() as db:
            assert db is not None
            assert registry.snapshot_counts()["active_leases"] == 1
        with factory() as db:
            assert db is not None
        assert authority.calls == before + 2
        assert registry.snapshot_counts()["active_leases"] == 0
    finally:
        registry.close()


def test_fails_closed_on_central_outage_and_epoch_revocation(monkeypatch):
    authority, registry, fake, trusted = setup(monkeypatch)
    factory = EpochGuardedSessionFactory(registry, trusted.tenant_id)
    try:
        authority.broken = True
        with pytest.raises(LookupError):
            with factory():
                pass
        assert registry.snapshot_counts()["active_leases"] == 0
        authority.broken = False
        with factory() as db:
            assert db is not None
            authority.states[TID_A] = EpochState(2, False)
            with pytest.raises(LookupError):
                with factory():
                    pass
            assert registry.snapshot_counts()["draining_pools"] == 1
        assert registry.snapshot_counts()["draining_pools"] == 0
    finally:
        registry.close()


def test_staged_http_does_not_fallback_to_global_pool_after_control_outage(monkeypatch):
    authority, registry, fake, trusted = setup(monkeypatch)
    try:
        client = TestClient(build(registry, trusted))
        authority.broken = True
        resp = client.post("/api/v1/auth/login", json={
            "tenant_slug": trusted.slug,
            "email": "synthetic-user@invalid.test",
            "password": "a-secret-password-candidate",
        })
        assert resp.status_code == 401
        assert "token" not in resp.text
        # Invalid signed credential is denied before any pool fallback.
        resp = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "fake-token-" + "x"*80,
        })
        assert resp.status_code == 401
        assert registry.snapshot_counts()["active_leases"] == 0
    finally:
        registry.close()


def test_bridge_refuses_duplicate_aliases_or_tenant_id_mismatch(monkeypatch):
    authority, registry, fake, trusted = setup(monkeypatch)
    try:
        bad = replace(trusted, tenant_id=TID_B)
        with pytest.raises(ValueError):
            create_clone_preauth_pilot(
                registry=registry,
                provisioned={trusted.tenant_id: bad},
                keyring=TenantRouteKeyring({"v1": bytes(range(32))}, "v1"),
                meta_app_secret="synthetic-secret-adequate-length",
            )
    finally:
        registry.close()
