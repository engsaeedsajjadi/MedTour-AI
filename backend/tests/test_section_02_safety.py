"""Section 02 regression: consent precedence, no automated PHI release, no alpha production."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.safety_rules import assert_safe_runtime, public_safety_contract
from app.models import Consent
from app.enterprise_models import TranslationDraft


def grant(client, headers, patient_id, purpose, accepted=True):
    response = client.post(
        "/api/v1/consents", headers=headers,
        json={"patient_id": patient_id, "purpose": purpose,
              "accepted": accepted, "notice_version": "v2"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_draft(client, headers, patient_id, monkeypatch):
    grant(client, headers, patient_id, "communication")
    grant(client, headers, patient_id, "ai_processing")
    conversation = client.post(
        "/api/v1/conversations", headers=headers,
        json={"patient_id": patient_id}
    )
    assert conversation.status_code == 201
    monkeypatch.setattr(
        "app.communications.translate",
        lambda *_: "Synthetic draft for human review"
    )
    response = client.post(
        "/api/v1/communications/translation-drafts", headers=headers,
        json={
            "conversation_id": conversation.json()["id"],
            "source_language": "fa", "target_language": "ps",
            "source_text": "SYNTHETIC CONTENT ONLY"
        }
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def review(client, headers, draft_id):
    return client.post(
        f"/api/v1/communications/translation-drafts/{draft_id}/review",
        headers=headers,
        json={"action": "approve", "approved_text": "Human-approved synthetic text"}
    )


def test_alpha_production_is_unconditionally_denied(monkeypatch):
    assert_safe_runtime("test")
    assert_safe_runtime("development")
    monkeypatch.setenv("MEDTOUR_PRODUCTION_AUTHORIZED", "true")
    monkeypatch.setenv("PRODUCTION_READY", "true")
    with pytest.raises(RuntimeError, match="NOT authorized"):
        assert_safe_runtime("production")


def test_public_contract_fails_closed(context):
    client, _, _, _ = context
    response = client.get("/api/v1/safety/contract")
    assert response.status_code == 200
    policy = response.json()
    assert policy == public_safety_contract()
    assert policy["production_ready"] is False
    assert policy["real_patient_data_allowed"] is False
    assert policy["automatic_diagnosis_allowed"] is False
    assert policy["clinical_decisions_require_qualified_human"] is True


def test_staff_withdrawal_blocks_scrubs_and_prevents_later_ai_review(seeded, monkeypatch):
    (client, auth, _, Session), admin, patient, _ = seeded
    draft = make_draft(client, admin, patient["id"], monkeypatch)
    before = review(client, auth("b"), draft)
    assert before.status_code == 404
    grant(client, admin, patient["id"], "ai_processing", accepted=False)
    with Session() as db:
        row = db.scalar(select(TranslationDraft).where(TranslationDraft.id == draft))
        assert row.status == "blocked"
        assert row.source_text == ""
        assert row.draft_text == ""
    assert review(client, admin, draft).status_code == 409
    # New consent may enable NEW drafts; it cannot resurrect previously blocked drafts.
    grant(client, admin, patient["id"], "ai_processing")
    assert review(client, admin, draft).status_code == 409


def test_patient_link_withdrawal_same_guards_tenant_scoped(seeded, monkeypatch):
    (client, auth, _, Session), admin, patient, _ = seeded
    draft = make_draft(client, admin, patient["id"], monkeypatch)
    other = client.post(
        "/api/v1/patients", headers=admin,
        json={"full_name": "Second Synthetic Patient", "language": "ar"}
    ).json()
    other_draft = make_draft(client, admin, other["id"], monkeypatch)
    issued = client.post(
        f"/api/v1/consent-links/{patient['id']}/communication", headers=admin
    )
    assert issued.status_code == 201
    response = client.post(
        "/api/v1/consent-links/respond",
        json={"token": issued.json()["token"], "notice_version": "v3",
              "accepted": False}
    )
    assert response.status_code == 201, response.text
    with Session() as db:
        affected = db.get(TranslationDraft, draft)
        unaffected = db.get(TranslationDraft, other_draft)
        assert (affected.status, affected.source_text, affected.draft_text) == (
            "blocked", "", ""
        )
        assert unaffected.status == "pending_review"
        assert unaffected.draft_text
    assert review(client, admin, draft).status_code == 409
    assert review(client, admin, other_draft).status_code == 200


def test_review_requires_fresh_ai_processing_consent_not_only_chat_consent(seeded, monkeypatch):
    (client, auth, _, Session), admin, patient, _ = seeded
    draft = make_draft(client, admin, patient["id"], monkeypatch)
    # Simulate a legacy direct-write revocation which bypassed the endpoint's
    # cancellation handler. Publication MUST STILL check the latest consent.
    with Session() as db:
        tenant_id = db.get(TranslationDraft, draft).tenant_id
        db.add(Consent(tenant_id=tenant_id,
            patient_id=patient["id"], purpose="ai_processing",
            accepted=False, notice_version="legacy-test"))
        db.commit()
    refused = review(client, admin, draft)
    assert refused.status_code == 409, refused.text
    assert "AI processing consent" in str(refused.json()["detail"])

def test_ai_endpoint_must_be_exact_preapproved_public_https_host(monkeypatch):
    from app.ai import approved_provider_base_url, provider_available
    monkeypatch.setenv("AI_PROVIDER_APPROVED", "true")
    monkeypatch.setenv("AI_API_KEY", "synthetic-unit-test-key")
    monkeypatch.setenv("AI_MODEL", "synthetic-model")
    monkeypatch.setenv("AI_APPROVED_HOSTS", "api.example.com")
    allowed = "https://api.example.com/v1"
    monkeypatch.setenv("AI_BASE_URL", allowed)
    assert approved_provider_base_url() == allowed
    assert provider_available()
    for endpoint in (
        "http://api.example.com/v1",
        "https://api.example.com.evil.net/v1",
        "https://127.0.0.1/v1",
        "https://localhost/v1",
        "https://api.example.com:8443/v1",
        "https://user:pass@api.example.com/v1",
        "https://api.example.com/v1?token=secret",
        "https://api.example.com/v1#fragment",
    ):
        monkeypatch.setenv("AI_BASE_URL", endpoint)
        assert approved_provider_base_url() is None, endpoint
        assert not provider_available(), endpoint
    monkeypatch.setenv("AI_BASE_URL", allowed)
    monkeypatch.delenv("AI_APPROVED_HOSTS")
    assert not provider_available()
