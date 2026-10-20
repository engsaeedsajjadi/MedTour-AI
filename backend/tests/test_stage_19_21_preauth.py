"""Offline failure-path tests for staged pre-auth tenant-role flow."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.staged_preauth_service import StagedPreAuthService
from app.staged_preauth_http import staged_preauth_router
from app.tenant_route_tokens import TenantRouteKeyring

TID = "11111111-1111-4111-8111-111111111111"
TID_OTHER = "22222222-2222-4222-8222-222222222222"
SECRET = "synthetic-meta-test-signature-secret-value"


class ShouldNotConnect:
    def __call__(self):
        raise AssertionError("Untrusted credential unexpectedly created a DB session")


def service(*, approved=True, phone=None):
    return StagedPreAuthService(
        keyring=TenantRouteKeyring({"v1": bytes(range(32))}, "v1"),
        sessions_by_tenant={TID: ShouldNotConnect()},
        tenant_slugs={"safe-tenant": TID},
        whatsapp_accounts=phone if phone is not None else {"safe-phone": TID},
        whatsapp_app_secret=SECRET,
        whatsapp_approved=approved,
    )


def signature(data: bytes, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


def payload(accounts):
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {"metadata": {"phone_number_id": account}},
            } for account in accounts],
        }],
    }).encode("utf-8")


def test_unknown_slug_does_not_query_any_database():
    svc = service()
    assert svc.login("unknown", "user@example.invalid", "candidate-password") is None


def test_signed_refresh_with_other_tenant_has_no_available_pool():
    svc = service()
    other = svc._keyring.issue(
        purpose="refresh", tenant_id=TID_OTHER, ttl_seconds=1800
    )
    assert svc.refresh(other) is None
    assert svc.refresh("legacy-" + "A" * 60) is None


def test_invalid_meta_signature_and_unknown_account_are_denied_before_db():
    svc = service()
    known = payload(["safe-phone"])
    assert svc.verify_webhook_route(known, signature(known, "wrong-secret-value")) is None
    unknown = payload(["foreign-phone"])
    assert svc.verify_webhook_route(unknown, signature(unknown)) is None


def test_mixed_account_signed_payload_denied_before_db():
    svc = service(phone={"safe-phone": TID, "foreign-phone": TID})
    mixed = payload(["safe-phone", "foreign-phone"])
    assert svc.verify_webhook_route(mixed, signature(mixed)) is None


def test_approval_gate_denies_even_valid_signed_meta_webhook():
    svc = service(approved=False)
    known = payload(["safe-phone"])
    assert svc.verify_webhook_route(known, signature(known)) is None


@pytest.mark.parametrize("registry", [
    {"safe-tenant": TID_OTHER}, {"bad-tenant": "invalid-uuid"}
])
def test_unprovisioned_slug_registration_fails_at_startup(registry):
    with pytest.raises(ValueError):
        StagedPreAuthService(
            keyring=TenantRouteKeyring({"v1": bytes(range(32))}, "v1"),
            sessions_by_tenant={TID: ShouldNotConnect()},
            tenant_slugs=registry,
            whatsapp_accounts={},
            whatsapp_app_secret=SECRET,
        )


def test_staged_http_endpoints_reject_unknown_login_refresh_and_webhook():
    app = FastAPI()
    app.include_router(staged_preauth_router(service()))
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/v1/auth/login", json={
            "tenant_slug": "unknown",
            "email": "user@example.invalid",
            "password": "synthetic-password",
        })
        assert login.status_code == 401
        refresh = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "legacy-" + "A" * 60,
        })
        assert refresh.status_code == 401
        raw = payload(["safe-phone"])
        response = client.post(
            "/api/v1/webhooks/whatsapp", content=raw,
            headers={"X-Hub-Signature-256": signature(raw, "wrong-secret-value")},
        )
        assert response.status_code == 403
