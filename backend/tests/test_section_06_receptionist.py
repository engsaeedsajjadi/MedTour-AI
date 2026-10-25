"""Section 06 synthetic multilingual administrative routing; never clinical QA."""
import pytest

from app.intake import EMERGENCY, INTAKE_QUESTIONS, LANGUAGES, normalize_safety_text
from app.receptionist import (
    LABELS, DIRECTION, RESPONSES, classify_intent, receptionist_response
)


@pytest.mark.parametrize("lang", sorted(LANGUAGES))
def test_all_five_languages_have_complete_receptionist_copy(lang):
    assert lang in LABELS
    assert DIRECTION[lang] == ("ltr" if lang == "en" else "rtl")
    assert set(RESPONSES[lang]) == {
        "greeting", "appointment", "quote", "documents", "visa",
        "human", "general"
    }
    assert len(INTAKE_QUESTIONS[lang]) == 5
    for intent, answer in RESPONSES[lang].items():
        assert isinstance(answer, str)
        assert 40 <= len(answer) <= 450, (lang, intent)
        assert "synthetic" not in answer.lower()


@pytest.mark.parametrize("lang,text,expected", [
    ("fa", "سلام", "greeting"),
    ("ar", "مرحبا", "greeting"),
    ("en", "Hello", "greeting"),
    ("ps", "سلامونه", "greeting"),
    ("prs", "سلام", "greeting"),
    ("fa", "می‌خواهم با اپراتور صحبت کنم", "human"),
    ("ar", "أريد التحدث مع شخص حقيقي", "human"),
    ("en", "I want a human operator", "human"),
    ("ps", "د انسان سره خبرې غواړم", "human"),
    ("prs", "یک کارمند انسانی می‌خواهم", "human"),
    ("en", "How much does a consultation cost?", "quote"),
    ("ar", "كم السعر", "quote"),
    ("fa", "برای نوبت داکتر", "appointment"),
    ("ps", "د ډاکټر وخت", "appointment"),
    ("prs", "اسناد طبی", "documents"),
    ("en", "Do I need a visa?", "visa"),
])
def test_deterministic_admin_intents(lang, text, expected):
    result = receptionist_response(lang, text)
    assert result["intent"] == expected, (lang, text, result)
    assert result["language"] == lang
    assert result["message"] == RESPONSES[lang][expected]
    assert result["provider_called"] is False
    assert result["automatic_clinical_decision"] is False
    assert result["human_review_required"] is True


def test_emergency_matching_handles_arabic_persian_unicode_and_cross_language():
    assert normalize_safety_text("تنگی‌نَفَس   شدید") == normalize_safety_text("تنگی نفس شدید")
    phrases = [
        ("ar", "أَلَمٌ فِي الصَّدْرِ"),
        ("fa", "درد قفسه سينه"),
        ("prs", "نفس‌تنگی شدید"),
        ("ps", "د سینې درد"),
        ("en", "I CAN'T BREATHE"),
        ("en", "خونریزی شدید"),
    ]
    for locale, phrase in phrases:
        response = receptionist_response(locale, phrase)
        assert response["intent"] == "urgent_human_review"
        assert response["emergency_keyword_detected"] is True
        assert response["human_handoff_required"] is True
        assert response["provider_called"] is False
        assert response["message"]
    # This lexical check is precautionary; never claim it detects all emergencies.


def test_unknown_language_and_invalid_content_fail_closed():
    with pytest.raises(ValueError):
        receptionist_response("de", "Hello")
    with pytest.raises(ValueError):
        receptionist_response("en", " ")
    with pytest.raises(ValueError):
        receptionist_response("en", "x" * 4001)
    assert classify_intent("No specific administrative category") == "general"


def test_catalog_and_preview_are_staff_only_and_exclude_patient_text(context):
    client, auth, _, _ = context
    assert client.get("/api/v1/receptionist/catalog").status_code == 401
    assert client.post("/api/v1/receptionist/preview", json={
        "language": "fa", "intent": "greeting"
    }).status_code == 401
    admin = auth("a")
    catalog = client.get("/api/v1/receptionist/catalog", headers=admin)
    assert catalog.status_code == 200
    assert {x["code"] for x in catalog.json()["supported_languages"]} == LANGUAGES
    assert all(not x["copy_reviewed_by_native_speaker"]
               for x in catalog.json()["supported_languages"])
    assert not catalog.json()["speech_enabled"]
    assert not catalog.json()["clinical_translation_validated"]
    assert not catalog.json()["production_ready"]
    assert client.get("/api/v1/receptionist/catalog", headers=auth("a", "operator@example.test")).status_code == 200
    assert client.post("/api/v1/receptionist/preview", headers=admin, json={
        "language": "fa", "intent": "not_a_real_intent"
    }).status_code == 422
    assert client.post("/api/v1/receptionist/preview", headers=admin, json={
        "language": "fa", "intent": "greeting", "source_text": "NO PATIENT TEXT ALLOWED"
    }).status_code == 422
    preview = client.post("/api/v1/receptionist/preview", headers=admin, json={
        "language": "ps", "intent": "appointment"
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["message"] == RESPONSES["ps"]["appointment"]
    assert preview.json()["external_message_sent"] is False


def _open_patient_session(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    approved = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "communication",
        "accepted": True, "notice_version": "v6"
    })
    assert approved.status_code == 201, approved.text
    invite = client.post("/api/v1/portal/invites/" + patient["id"], headers=admin)
    assert invite.status_code == 201, invite.text
    exchange=client.post("/api/v1/portal/session/exchange",json={
        "invitation_token":invite.json()["token"],
        "verification_code":invite.json()["demo_verification_code"]})
    assert exchange.status_code==201,exchange.text
    return client, auth, Session, admin, patient, case, {
        "X-Patient-Access": exchange.json()["access_token"]
    }


def test_portal_supports_language_switch_and_explicit_human_handoff(seeded):
    client, auth, Session, admin, patient, case, portal = _open_patient_session(seeded)
    first = client.post("/api/v1/portal/chat", headers=portal, json={
        "language": "ar", "message": "مرحبا"
    })
    assert first.status_code == 201, first.text
    assert first.json()["language"] == "ar"
    assert first.json()["intent"] == "greeting"
    assert first.json()["automated_response"] == RESPONSES["ar"]["greeting"]
    human = client.post("/api/v1/portal/chat", headers=portal, json={
        "language": "fa", "message": "با اپراتور صحبت کنم"
    })
    assert human.status_code == 201, human.text
    assert human.json()["human_handoff"] is True
    assert human.json()["automated_response"] is None
    assert human.json()["handoff_notice"] == RESPONSES["fa"]["human"]
    history = client.get("/api/v1/portal/chat", headers=portal)
    assert history.status_code == 200
    assert len(history.json()) == 3
    assert history.json()[0]["language"] == "ar"
    assert history.json()[-1]["language"] == "fa"
    assert client.post("/api/v1/portal/chat", headers=portal, json={
        "language": "unknown", "message": "Hello"
    }).status_code == 422
    assert client.post("/api/v1/portal/chat", headers={
        "X-Patient-Access": "invalid"
    }, json={"language": "fa", "message": "سلام"}).status_code == 401


def test_portal_emergency_handoff_uses_requested_locale(seeded):
    client, auth, Session, admin, patient, case, portal = _open_patient_session(seeded)
    outcome = client.post("/api/v1/portal/chat", headers=portal, json={
        "language": "ar", "message": "أَلَمٌ فِي الصَّدْرِ"
    })
    assert outcome.status_code == 201
    assert outcome.json()["warning"] is not None
    assert outcome.json()["human_handoff"] is True
    assert outcome.json()["automated_response"] is None
    assert outcome.json()["intent"] == "urgent_human_review"
    assert len(client.get("/api/v1/portal/chat", headers=portal).json()) == 1


def test_portal_refuses_chat_without_active_communication_consent(seeded):
    client, auth, Session, admin, patient, case, portal = _open_patient_session(seeded)
    cancelled = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "communication",
        "accepted": False, "notice_version": "v7"
    })
    assert cancelled.status_code == 201
    assert client.post("/api/v1/portal/chat", headers=portal, json={
        "language": "en", "message": "Hello"
    }).status_code == 401


def test_ai_draft_bypasses_provider_on_urgent_or_explicit_human_request(seeded, monkeypatch):
    (client, auth, _, Session), admin, patient, case = seeded
    granted = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "ai_processing",
        "accepted": True, "notice_version": "v6"
    })
    assert granted.status_code == 201
    def forbidden(*args, **kwargs):
        raise AssertionError("Unreviewed human/urgent message reached AI provider")
    monkeypatch.setattr("app.main.ai_draft", forbidden)
    for message, expected in (
        ("I cannot breathe", "urgent_human_review"),
        ("I want a human operator", "human"),
    ):
        r = client.post("/api/v1/intake/ai-draft", headers=admin, json={
            "case_id": case["id"], "language": "en", "message": message
        })
        assert r.status_code == 200, r.text
        assert r.json()["intent"] == expected
        assert r.json()["provider_called"] is False
        assert r.json()["human_handoff_required"] is True
