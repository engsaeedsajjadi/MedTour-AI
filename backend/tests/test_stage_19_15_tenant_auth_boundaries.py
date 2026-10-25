"""Stage 19.15 — synthetic API tenant-boundary regression tests.

These tests run against the existing SQLite TestClient fixture only.
They verify present-day application-layer boundaries and deliberately do NOT
assert that the production PostgreSQL role-routing/RLS integration is complete.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import jwt
from sqlalchemy import select

from app.enterprise_models import MessageEvent
from app.models import Message


def _make_patient(client, headers, name: str, contact: str = "") -> str:
    response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={"full_name": name, "country": "AF", "language": "en", "contact": contact},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _accept_communication(client, headers, patient_id: str) -> None:
    response = client.post(
        "/api/v1/consents",
        headers=headers,
        json={
            "patient_id": patient_id,
            "purpose": "communication",
            "accepted": True,
            "notice_version": "stage-19-15",
        },
    )
    assert response.status_code == 201, response.text


def test_validly_signed_jwt_with_wrong_tenant_id_is_denied(context):
    client, auth, (tenant_a, tenant_b), _ = context
    headers_a = auth("a")
    access_token = headers_a["Authorization"].split(" ", 1)[1]
    claims = jwt.decode(access_token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    claims["tid"] = tenant_b
    forged = jwt.encode(claims, os.environ["JWT_SECRET"], algorithm="HS256")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401, response.text
    valid = client.get("/api/v1/auth/me", headers=headers_a)
    assert valid.status_code == 200
    assert valid.json()["tenant_id"] == tenant_a


def test_login_does_not_authenticate_email_from_another_tenant(context):
    client, _, _, _ = context
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "b",
            "email": "a@example.test",
            "password": "test_password_12345",
        },
    )
    assert response.status_code == 401, response.text


def test_refresh_replay_in_a_does_not_revoke_b(context):
    client, _, _, _ = context
    def login(slug: str):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": slug,
                "email": f"{slug}@example.test",
                "password": "test_password_12345",
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["refresh_token"]

    refresh_a = login("a")
    refresh_b = login("b")
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_a})
    assert first.status_code == 200, first.text
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_a})
    assert replay.status_code == 401, replay.text
    still_valid_b = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_b})
    assert still_valid_b.status_code == 200, still_valid_b.text


def test_portal_link_remains_patient_and_tenant_bound(context):
    client, auth, _, _ = context
    ha, hb = auth("a"), auth("b")
    pa = _make_patient(client, ha, "Synthetic A Portal")
    pb = _make_patient(client, hb, "Synthetic B Portal")
    _accept_communication(client, ha, pa)
    _accept_communication(client, hb, pb)
    for h, pid in ((ha,pa),(hb,pb)):
        consent=client.post("/api/v1/consents",headers=h,json={
            "patient_id":pid,"purpose":"intake","accepted":True,
            "notice_version":"stage-19-15"})
        assert consent.status_code==201,consent.text

    foreign_invite = client.post(f"/api/v1/portal/invites/{pb}", headers=ha)
    assert foreign_invite.status_code == 404, foreign_invite.text

    issued_a = client.post(f"/api/v1/portal/invites/{pa}", headers=ha)
    issued_b = client.post(f"/api/v1/portal/invites/{pb}", headers=hb)
    assert issued_a.status_code == issued_b.status_code == 201
    def redeem(invite):
        data=invite.json()
        exchange=client.post("/api/v1/portal/session/exchange",json={
            "invitation_token":data["token"],
            "verification_code":data["demo_verification_code"]})
        assert exchange.status_code==201,exchange.text
        return exchange.json()["access_token"]
    tok_a, tok_b = redeem(issued_a), redeem(issued_b)

    me_a = client.get("/api/v1/portal/me", headers={"X-Patient-Access": tok_a})
    me_b = client.get("/api/v1/portal/me", headers={"X-Patient-Access": tok_b})
    assert me_a.status_code == me_b.status_code == 200
    assert me_a.json()["id"] == pa
    assert me_b.json()["id"] == pb

    revoke_a = client.post(f"/api/v1/portal/invites/revoke/{pa}", headers=ha)
    assert revoke_a.status_code == 200, revoke_a.text
    assert client.get("/api/v1/portal/me", headers={"X-Patient-Access": tok_a}).status_code == 401
    assert client.get("/api/v1/portal/me", headers={"X-Patient-Access": tok_b}).status_code == 200


def test_consent_link_replay_and_cross_tenant_issue_rejected(context):
    client, auth, _, _ = context
    ha, hb = auth("a"), auth("b")
    pa = _make_patient(client, ha, "Synthetic Consent A")
    pb = _make_patient(client, hb, "Synthetic Consent B")

    assert client.post(f"/api/v1/consent-links/{pb}/communication", headers=ha).status_code == 404
    issue = client.post(f"/api/v1/consent-links/{pa}/communication", headers=ha)
    assert issue.status_code == 201, issue.text
    token = issue.json()["token"]

    preview = client.get("/api/v1/consent-links/preview", params={"token": token})
    assert preview.status_code == 200, preview.text
    payload = {"token": token, "notice_version": "stage-19-15", "accepted": True}
    response = client.post("/api/v1/consent-links/respond", json=payload)
    assert response.status_code == 201, response.text
    assert client.post("/api/v1/consent-links/respond", json=payload).status_code == 401
    assert client.get("/api/v1/consent-links/preview", params={"token": token}).status_code == 401


def test_signed_whatsapp_webhook_cannot_route_b_patient_to_a(monkeypatch, context):
    client, auth, (tenant_a, tenant_b), Session = context
    hb = auth("b")
    phone = "15559001915"
    pb = _make_patient(client, hb, "Synthetic WhatsApp B", contact=phone)
    _accept_communication(client, hb, pb)

    settings = {
        "WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED": "true",
        "WHATSAPP_INBOUND_PROCESSING_APPROVED": "true",
        "META_APP_SECRET": "synthetic-stage-19-15-test-secret",
        "META_VERIFY_TOKEN": "synthetic-stage-19-15-verify",
        "WHATSAPP_TENANT_SLUG": "a",
        "WHATSAPP_PHONE_NUMBER_ID": "synthetic-whatsapp-a",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": settings["WHATSAPP_PHONE_NUMBER_ID"]},
                    "messages": [{
                        "id": "synthetic-msg-stage-19-15",
                        "from": phone,
                        "type": "text",
                        "text": {"body": "Synthetic consultation request"},
                    }],
                },
            }],
        }],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = "sha256=" + hmac.new(settings["META_APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

    first = client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["routed_to_human"] == 0
    assert first.json()["quarantined"] == 1
    second = client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["duplicates"] == 1

    with Session() as db:
        events = db.scalars(select(MessageEvent).where(MessageEvent.tenant_id == tenant_a)).all()
        assert len(events) == 1
        assert events[0].status == "quarantined_no_matching_consent"
        assert db.scalars(select(Message).where(Message.tenant_id == tenant_b)).all() == []
