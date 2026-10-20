"""Fast negative-path checks for stage 19.20 HTTP tenant router (no DB)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.staged_http_tenant_router import StagedHttpTenantRouter
from app.tenant_route_tokens import TenantRouteKeyring

TID = "11111111-1111-4111-8111-111111111111"


class NoConnectionAllowed:
    def __call__(self):
        raise AssertionError("Invalid or unsupported request unexpectedly opened a DB connection")


def offline_client():
    keyring = TenantRouteKeyring({"test1": bytes(range(32))}, "test1")
    app.dependency_overrides[get_db] = StagedHttpTenantRouter(
        keyring=keyring,
        sessions_by_tenant={TID: NoConnectionAllowed()},
    ).get_db
    return TestClient(app, raise_server_exceptions=False)


def test_bad_staff_jwt_and_tenant_header_cannot_route():
    try:
        with offline_client() as client:
            r = client.get("/api/v1/patients", headers={"X-Tenant-ID": TID})
            assert r.status_code == 401
            r = client.get(
                "/api/v1/patients",
                headers={"Authorization": "Bearer not-a-jwt", "X-Tenant-ID": TID},
            )
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_unsigned_legacy_portal_token_fails_closed():
    try:
        with offline_client() as client:
            response = client.get(
                "/api/v1/portal/me",
                headers={"X-Patient-Access": "legacy-" + "a" * 65},
            )
            assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_unsupported_login_and_refresh_routes_do_not_use_global_db():
    try:
        with offline_client() as client:
            login = client.post(
                "/api/v1/auth/login",
                json={
                    "tenant_slug": "untrusted",
                    "email": "test@example.invalid",
                    "password": "synthetic-password",
                },
            )
            assert login.status_code == 503
            refresh = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "a" * 70},
            )
            assert refresh.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_unmigrated_webhook_and_readiness_routes_fail_closed():
    try:
        with offline_client() as client:
            assert client.get("/api/v1/health/ready").status_code == 503
            assert client.post("/api/v1/webhooks/whatsapp", json={}).status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_unsigned_consent_link_does_not_query_database():
    try:
        with offline_client() as client:
            preview = client.get(
                "/api/v1/consent-links/preview",
                params={"token": "legacy-" + "b" * 65},
            )
            assert preview.status_code == 401
            response = client.post(
                "/api/v1/consent-links/respond",
                json={"token": "legacy-" + "c" * 65,
                      "notice_version": "stage20", "accepted": True},
            )
            assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_default_denial_for_another_db_using_staff_path():
    try:
        with offline_client() as client:
            response = client.get("/api/v1/physicians")
            # This route deliberately is not yet registered in the safe
            # routing allowlist, even if its original FastAPI code uses get_db.
            assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()
