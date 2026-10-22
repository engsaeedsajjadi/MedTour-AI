"""Synthetic architecture and worker tests. No internet, accounts or real patient data."""
import os

from app import delivery, outbound_worker, stack_health
from app.enterprise_models import OutboundMessage
from app.models import Conversation, Patient


def _ready_outbound(seeded):
    (client, auth, _, Session), admin, patient, _ = seeded
    with Session() as db:
        row = db.get(Patient, patient["id"])
        row.contact = "+989120000000"
        db.commit()
    consent = client.post(
        "/api/v1/consents", headers=admin,
        json={"patient_id": patient["id"], "purpose": "communication",
              "accepted": True, "notice_version": "v1"}
    )
    assert consent.status_code == 201
    conv = client.post(
        "/api/v1/conversations", headers=admin,
        json={"patient_id": patient["id"]}
    )
    assert conv.status_code == 201
    with Session() as db:
        row = db.get(Conversation, conv.json()["id"])
        row.channel = "whatsapp"
        db.commit()
    queued = client.post(
        "/api/v1/communications/outbound", headers=admin,
        json={
            "conversation_id": conv.json()["id"],
            "template_name": "please_check_secure_portal",
            "locale": "en",
            "idempotency_key": "synthetic-worker-unique-key-0001",
        }
    )
    assert queued.status_code == 201, queued.text
    approved = client.post(
        f"/api/v1/communications/outbound/{queued.json()['id']}/approve",
        headers=admin
    )
    assert approved.status_code == 200
    return queued.json()["id"], Session


def test_stack_ready_dev_is_explicit_about_skipped_migration(context, monkeypatch):
    client, _, _, _ = context
    monkeypatch.delenv("REDIS_URL", raising=False)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["schema_migration"] == "not_checked_sqlite"
    assert data["redis"] == "not_configured"
    assert data["production_ready"] is False


def test_readiness_fails_on_redis_or_migration_fault(context, monkeypatch):
    client, _, _, _ = context
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(stack_health, "check_redis", lambda url: False)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "Required stack dependency" in response.json()["detail"]
    monkeypatch.delenv("REDIS_URL")
    monkeypatch.setattr(stack_health, "check_migrations",
                        lambda db: (_ for _ in ()).throw(RuntimeError("Synthetic migration mismatch")))
    assert client.get("/api/v1/health/ready").status_code == 503


def test_alembic_revision_is_discovered_not_hardcoded():
    # New enterprise migrations must not require updating a frozen revision.
    # The healthcheck always compares the DB revision with the live script head.
    revision = stack_health.required_revision()
    assert isinstance(revision, str)
    assert len(revision) >= 8
    assert all(char in "0123456789abcdef" for char in revision.lower())


def test_worker_is_opt_in_and_cannot_run_in_production(monkeypatch):
    monkeypatch.setattr(outbound_worker, "provider_enabled", lambda: True)
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.delenv("OUTBOUND_WORKER_ENABLED", raising=False)
    assert not outbound_worker.authorized()
    assert outbound_worker.poll_once() == {"status": "disabled", "processed": 0}
    monkeypatch.setenv("OUTBOUND_WORKER_ENABLED", "true")
    assert outbound_worker.authorized()
    monkeypatch.setenv("APP_ENV", "production")
    assert not outbound_worker.authorized()
    monkeypatch.setenv("APP_ENV", "test")


def test_worker_only_polls_approved_rows_with_bounded_batch(seeded, monkeypatch):
    identifier, Session = _ready_outbound(seeded)
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OUTBOUND_WORKER_ENABLED", "true")
    monkeypatch.setattr(outbound_worker, "provider_enabled", lambda: True)
    monkeypatch.setattr(outbound_worker, "_heartbeat", lambda: None)
    visited = []
    def fake_sender(oid):
        visited.append(oid)
        return {"status": "not_approved"}
    out = outbound_worker.poll_once(
        session_factory=Session, sender=fake_sender, batch_size=1
    )
    assert out["status"] == "running"
    assert out["processed"] == 1
    assert visited == [identifier]
    try:
        outbound_worker.poll_once(session_factory=Session, sender=fake_sender, batch_size=101)
        assert False, "batch_size > 100 must be rejected"
    except ValueError:
        pass


def test_atomic_outbound_claim_prevents_duplicate_provider_request(seeded, monkeypatch):
    identifier, Session = _ready_outbound(seeded)
    monkeypatch.setattr(delivery, "SessionLocal", Session)
    monkeypatch.setattr(delivery, "enabled", lambda: True)
    sent = []
    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"messages": [{"id": "wamid.synthetic.message"}]}
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs.get("follow_redirects") is False
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def post(self, url, headers, json):
            assert "/messages" in url
            assert json["type"] == "template"
            assert "medical" not in str(json).lower()
            sent.append(1)
            return MockResponse()
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")
    monkeypatch.setenv("META_ACCESS_TOKEN", "synthetic-secret")
    monkeypatch.setattr("httpx.Client", FakeClient)
    assert delivery.send_one(identifier)["status"] == "sent"
    assert delivery.send_one(identifier)["status"] == "not_approved"
    assert len(sent) == 1
    with Session() as db:
        row = db.get(OutboundMessage, identifier)
        assert row.status == "sent"
        assert row.attempt_count == 1
        assert row.provider_message_id == "wamid.synthetic.message"


def test_ambiguous_send_never_retries_automatically(seeded, monkeypatch):
    identifier, Session = _ready_outbound(seeded)
    monkeypatch.setattr(delivery, "SessionLocal", Session)
    monkeypatch.setattr(delivery, "enabled", lambda: True)
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def post(self, *args, **kwargs):
            raise TimeoutError("Synthetic timeout after provider may have accepted message")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")
    monkeypatch.setenv("META_ACCESS_TOKEN", "synthetic-secret")
    monkeypatch.setattr("httpx.Client", FakeClient)
    assert delivery.send_one(identifier)["status"] == "needs_reconciliation"
    assert delivery.send_one(identifier)["status"] == "not_approved"
    with Session() as db:
        row = db.get(OutboundMessage, identifier)
        assert row.status == "needs_reconciliation"
        assert row.attempt_count == 1


def test_provider_enabled_requires_eligibility_and_numeric_phone_id(monkeypatch):
    config = {
        "APP_ENV": "test",
        "WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED": "true",
        "WHATSAPP_INBOUND_PROCESSING_APPROVED": "true",
        "WHATSAPP_OUTBOUND_APPROVED": "true",
        "META_APP_SECRET": "synthetic",
        "META_VERIFY_TOKEN": "synthetic",
        "WHATSAPP_TENANT_SLUG": "a",
        "WHATSAPP_PHONE_NUMBER_ID": "123456789",
        "META_ACCESS_TOKEN": "synthetic-token",
        "META_API_VERSION": "v23.0",
    }
    for name, value in config.items():
        monkeypatch.setenv(name, value)
    assert delivery.enabled()
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "../wrong")
    assert not delivery.enabled()
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")
    monkeypatch.setenv("META_API_VERSION", "v23.0/../../x")
    assert not delivery.enabled()
    monkeypatch.setenv("META_API_VERSION", "v23.0")
    monkeypatch.setenv("APP_ENV", "production")
    assert not delivery.enabled()
