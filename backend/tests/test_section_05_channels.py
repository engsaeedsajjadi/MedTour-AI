"""Section 05 synthetic channel tests: no real Meta or Telegram access."""
import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Audit, Task
from app.enterprise_models import MessageEvent, OutboundMessage


def _configure_whatsapp(monkeypatch, *, tenant="a"):
    flags = {
        "WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED": "true",
        "WHATSAPP_INBOUND_PROCESSING_APPROVED": "true",
        "META_APP_SECRET": "synthetic-section05-secret",
        "META_VERIFY_TOKEN": "synthetic-section05-verification",
        "WHATSAPP_TENANT_SLUG": tenant,
        "WHATSAPP_PHONE_NUMBER_ID": "unit-test-phone-05",
    }
    for name, value in flags.items():
        monkeypatch.setenv(name, value)


def _signed_post(client, payload):
    raw = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(
        b"synthetic-section05-secret", raw, hashlib.sha256
    ).hexdigest()
    return client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )


def _receipt(provider_id, state):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "unit-test-phone-05"},
            "statuses": [{"id": provider_id, "status": state}],
        }}]}],
    }


def test_standalone_whatsapp_public_gateway_routes_and_alpha_gate(context):
    from app.whatsapp_entrypoint import app as ingress
    assert {(r.path, tuple(sorted(r.methods))) for r in ingress.routes} == {
        ("/api/v1/webhooks/whatsapp", ("GET",)),
        ("/api/v1/webhooks/whatsapp", ("POST",)),
    }
    standalone = TestClient(ingress)
    for path in (
        "/docs", "/openapi.json", "/api/v1/patients",
        "/api/v1/auth/login", "/api/v1/channels/readiness",
    ):
        assert standalone.get(path).status_code == 404
    assert standalone.post("/api/v1/portal/chat", json={}).status_code == 404


def test_gateway_signed_receipts_are_deduped_and_monotonic(seeded, monkeypatch):
    (client, auth, ids, Session), admin, patient, case = seeded
    _configure_whatsapp(monkeypatch)
    with Session() as db:
        outgoing = OutboundMessage(
            tenant_id=ids[0], patient_id=patient["id"],
            conversation_id=client.post(
                "/api/v1/conversations", headers=admin,
                json={"patient_id": patient["id"]}
            ).json()["id"] if False else None,
        )
    # Build with a real tenant-owned conversation, no provider network.
    conv = client.post(
        "/api/v1/conversations", headers=admin,
        json={"patient_id": patient["id"]},
    ).json()
    with Session() as db:
        outgoing = OutboundMessage(
            tenant_id=ids[0], patient_id=patient["id"],
            conversation_id=conv["id"], template_name="case_update_available",
            idempotency_key="synthetic-receipt-123456",
            locale="en", status="sent",
            provider_message_id="wamid.synthetic.section05",
            approved_by=db.scalar(select(Audit.user_id).where(
                Audit.tenant_id == ids[0]).limit(1)),
        )
        db.add(outgoing)
        db.commit()
        outbound_id = outgoing.id

    assert _signed_post(client, _receipt("wamid.synthetic.section05", "delivered")).json()["receipts_processed"] == 1
    assert _signed_post(client, _receipt("wamid.synthetic.section05", "delivered")).json()["receipts_processed"] == 0
    assert _signed_post(client, _receipt("wamid.synthetic.section05", "read")).status_code == 200
    assert _signed_post(client, _receipt("wamid.synthetic.section05", "delivered")).status_code == 200
    with Session() as db:
        assert db.get(OutboundMessage, outbound_id).status == "read"
        events = db.scalars(select(MessageEvent).where(
            MessageEvent.tenant_id == ids[0],
            MessageEvent.status.in_(["delivery_delivered", "delivery_read"])
        )).all()
        assert len(events) == 2
        assert all("wamid" not in event.event_id for event in events)


def test_failed_receipt_requests_reconciliation_not_retransmission(seeded, monkeypatch):
    (client, auth, ids, Session), admin, patient, case = seeded
    _configure_whatsapp(monkeypatch)
    conv = client.post("/api/v1/conversations", headers=admin,
                       json={"patient_id": patient["id"]}).json()
    with Session() as db:
        item = OutboundMessage(
            tenant_id=ids[0], patient_id=patient["id"],
            conversation_id=conv["id"], idempotency_key="synthetic-failed-1234",
            template_name="case_update_available", locale="en",
            status="sent", provider_message_id="wamid.synthetic.fail05",
        )
        db.add(item)
        db.commit()
        identifier = item.id
    response = _signed_post(client, _receipt("wamid.synthetic.fail05", "failed"))
    assert response.status_code == 200, response.text
    with Session() as db:
        item = db.get(OutboundMessage, identifier)
        assert item.status == "needs_reconciliation"
        assert item.last_error_code == "PROVIDER_REPORTED_FAILURE"
        assert item.attempt_count == 0


def test_webhook_does_not_accept_wrong_account_or_content_type(seeded, monkeypatch):
    (client, auth, _, _), admin, patient, case = seeded
    _configure_whatsapp(monkeypatch)
    payload = _receipt("wamid.synthetic.unknown", "delivered")
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "other-tenant-phone"
    assert _signed_post(client, payload).status_code == 403
    raw = json.dumps(_receipt("wamid.synthetic.unknown", "read")).encode()
    sig = "sha256=" + hmac.new(b"synthetic-section05-secret", raw, hashlib.sha256).hexdigest()
    assert client.post("/api/v1/webhooks/whatsapp", content=raw,
                       headers={"X-Hub-Signature-256": sig,
                                "Content-Type": "text/plain"}).status_code == 415
    malformed = {"object": "whatsapp_business_account", "entry": "not a list"}
    assert _signed_post(client, malformed).status_code == 422


def test_duplicate_inbound_event_in_same_payload_routes_only_once(seeded, monkeypatch):
    (client, auth, _, Session), admin, patient, case = seeded
    _configure_whatsapp(monkeypatch)
    with Session() as db:
        from app.models import Patient
        p = db.get(Patient, patient["id"])
        p.contact = "+12345678901"
        db.commit()
    consent = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "communication",
        "accepted": True, "notice_version": "test5",
    })
    assert consent.status_code == 201
    incoming = {"id": "wamid.synthetic.duplicate05",
                "from": "12345678901", "type": "text",
                "text": {"body": "Synthetic hello"}}
    raw = {"object": "whatsapp_business_account",
           "entry": [{"changes": [{"field": "messages", "value": {
               "metadata": {"phone_number_id": "unit-test-phone-05"},
               "messages": [incoming, incoming],
           }}]}]}
    first = _signed_post(client, raw)
    assert first.status_code == 200, first.text
    assert first.json()["routed_to_human"] == 1
    assert first.json()["duplicates"] == 1


def test_channel_options_and_fallback_require_own_tenant_and_consent(seeded):
    (client, auth, ids, Session), admin, patient, case = seeded
    unread = client.get("/api/v1/channels/readiness", headers=admin)
    assert unread.status_code == 200
    assert unread.json()["primary"] == "whatsapp"
    assert unread.json()["automatic_channel_fallback"] is False
    assert unread.json()["channels"]["telegram"]["patient_data_approved"] is False
    assert client.get("/api/v1/channels/readiness").status_code == 401
    assert client.get("/api/v1/channels/patients/"+patient["id"]+"/options",
                      headers=auth("b")).status_code == 404
    url = "/api/v1/channels/cases/"+case["id"]+"/secure-portal-handoff"
    assert client.post(url, headers=admin).status_code == 409
    assert client.post(url, headers=auth("b")).status_code == 404
    client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "communication",
        "accepted": True, "notice_version": "v5",
    })
    options = client.get(
        "/api/v1/channels/patients/"+patient["id"]+"/options", headers=admin
    ).json()
    assert options["secure_portal_invitation_permitted"] is True
    assert options["telegram_patient_routing_supported"] is False
    one = client.post(url, headers=admin)
    assert one.status_code == 201, one.text
    assert one.json()["sent"] is False and not one.json()["portal_token_issued"]
    second = client.post(url, headers=admin)
    assert second.status_code == 201
    assert second.json()["task_id"] == one.json()["task_id"]
    assert second.json()["deduplicated"] is True
    with Session() as db:
        assert db.get(Task, one.json()["task_id"]).status == "open"
        audit = db.scalars(select(Audit).where(
            Audit.tenant_id == ids[0],
            Audit.event == "secure_portal_handoff_requested",
        )).all()
        assert len(audit) == 1
    withdraw = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "communication",
        "accepted": False, "notice_version": "v6",
    })
    assert withdraw.status_code == 201
    with Session() as db:
        assert db.get(Task, one.json()["task_id"]).status == "cancelled"
    assert client.post(url, headers=admin).status_code == 409
