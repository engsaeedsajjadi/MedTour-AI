"""Section 07 synthetic intake coordination tests, never clinical sign-off."""
from app.enterprise_models import CaseTimeline, PatientIntake
from app.models import Audit


def _patient_access(client, admin, patient_id):
    result = client.post(
        "/api/v1/consents", headers=admin,
        json={"patient_id": patient_id, "purpose": "communication",
              "accepted": True, "notice_version": "synthetic-v7"},
    )
    assert result.status_code == 201
    invite = client.post(
        f"/api/v1/portal/invites/{patient_id}", headers=admin
    )
    assert invite.status_code == 201
    exchange=client.post("/api/v1/portal/session/exchange",json={
        "invitation_token":invite.json()["token"],
        "verification_code":invite.json()["demo_verification_code"]})
    assert exchange.status_code==201,exchange.text
    return {"X-Patient-Access": exchange.json()["access_token"]}


def _staff_session(client, admin, case_id, locale="en"):
    result = client.post(
        "/api/v1/intake/sessions", headers=admin,
        json={"case_id": case_id, "language": locale},
    )
    assert result.status_code == 201, result.text
    return result.json()


def _complete(client, admin, session_id):
    for index in range(5):
        response = client.post(
            f"/api/v1/intake/sessions/{session_id}/answer",
            headers=admin,
            json={"answer": f"Synthetic administrative response {index}"},
        )
        assert response.status_code == 200, response.text
    assert response.json()["status"] == "awaiting_clinician_review"


def test_staff_and_patient_starts_share_one_session(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    portal = _patient_access(client, admin, patient["id"])
    first = _staff_session(client, admin, case["id"], "ps")
    resumed = client.post(
        "/api/v1/portal/intake/sessions", headers=portal,
        json={"case_id": case["id"], "language": "ps"},
    )
    assert resumed.status_code == 201, resumed.text
    assert resumed.json()["id"] == first["id"]
    assert _staff_session(client, admin, case["id"], "ps")["reused"]
    different = client.post(
        "/api/v1/intake/sessions", headers=admin,
        json={"case_id": case["id"], "language": "ar"},
    )
    assert different.status_code == 409
    with Session() as db:
        assert db.query(PatientIntake).count() == 1


def test_cannot_bypass_emergency_by_opening_staff_or_patient_session(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    portal = _patient_access(client, admin, patient["id"])
    session = _staff_session(client, admin, case["id"])
    flagged = client.post(
        f"/api/v1/intake/sessions/{session['id']}/answer",
        headers=admin, json={"answer": "I have chest pain"},
    )
    assert flagged.status_code == 200
    assert flagged.json()["emergency_keyword_detected"] is True
    assert client.post(
        "/api/v1/intake/sessions", headers=admin,
        json={"case_id": case["id"], "language": "en"},
    ).status_code == 409
    assert client.post(
        "/api/v1/portal/intake/sessions", headers=portal,
        json={"case_id": case["id"], "language": "en"},
    ).status_code == 409
    refused = client.post(
        f"/api/v1/intake-coordination/sessions/{session['id']}/review",
        headers=admin,
        json={"action": "record_handoff", "reference": "ADMIN-REVIEW-07"},
    )
    assert refused.status_code == 409
    status = client.get(
        f"/api/v1/intake-coordination/cases/{case['id']}", headers=admin
    ).json()
    assert status["urgency_keyword_alert"] is True
    assert status["clinical_validation"] == "not_performed"


def test_administrative_review_requests_more_info_and_latest_intake_replaces_old(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    session = _staff_session(client, admin, case["id"])
    _complete(client, admin, session["id"])
    operator = auth("a", "operator@example.test")
    handoff = client.post(
        f"/api/v1/intake-coordination/sessions/{session['id']}/review",
        headers=operator,
        json={"action": "record_handoff", "reference": "HANDOFF-0007"},
    )
    assert handoff.status_code == 403
    returned = client.post(
        f"/api/v1/intake-coordination/sessions/{session['id']}/review",
        headers=operator,
        json={"action": "request_more_information", "reference": "MOREINFO-0007"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["clinical_decision"] is False
    assert returned.json()["status"] == "needs_more_information"
    assert client.post(
        f"/api/v1/intake-coordination/sessions/{session['id']}/review",
        headers=operator,
        json={"action": "request_more_information", "reference": "MOREINFO-0007"},
    ).status_code == 409

    # Create a replacement version; an earlier complete session must NOT count
    # toward readiness while the current version is still incomplete.
    newer = _staff_session(client, admin, case["id"])
    assert newer["id"] != session["id"]
    mission = client.get(
        f"/api/v1/cases/{case['id']}/mission", headers=admin
    ).json()
    assert mission["conditions"]["intake_submitted"] is False
    _complete(client, admin, newer["id"])
    assert client.get(
        f"/api/v1/cases/{case['id']}/mission", headers=admin
    ).json()["conditions"]["intake_submitted"] is True

    handoff = client.post(
        f"/api/v1/intake-coordination/sessions/{newer['id']}/review",
        headers=admin,
        json={"action": "record_handoff", "reference": "HUMAN-ADMIN-007"},
    )
    assert handoff.status_code == 200
    assert handoff.json()["status"] == "handoff_recorded"
    assert handoff.json()["clinical_decision"] is False
    assert handoff.json()["external_clinician_confirmed"] is False
    assert client.get(
        f"/api/v1/cases/{case['id']}/mission", headers=admin
    ).json()["conditions"]["intake_submitted"] is True
    with Session() as db:
        audits = db.query(Audit).filter(
            Audit.event == "intake_administrative_review_recorded"
        ).all()
        events = db.query(CaseTimeline).filter(
            CaseTimeline.event == "intake_administrative_review"
        ).all()
        assert len(audits) == len(events) == 2
        assert "MOREINFO-0007" in events[0].details
        assert "HUMAN-ADMIN-007" in events[1].details


def test_intake_queue_is_staff_only_tenant_scoped_and_no_raw_answers(seeded):
    (client, auth, _, _), admin, patient, case = seeded
    session = _staff_session(client, admin, case["id"], "fa")
    _complete(client, admin, session["id"])
    path = "/api/v1/intake-coordination/queue"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth("b")).json()["items"] == []
    result = client.get(path, headers=admin)
    assert result.status_code == 200
    items = result.json()["items"]
    assert len(items) == 1
    assert items[0]["case_id"] == case["id"]
    assert items[0]["clinical_validation"] == "not_performed"
    assert "answers" not in str(result.json())
    assert "Synthetic administrative response" not in str(result.json())
    other = client.get(
        f"/api/v1/intake-coordination/cases/{case['id']}",
        headers=auth("b"),
    )
    assert other.status_code == 404
    assert client.get(
        f"/api/v1/intake-coordination/cases/{case['id']}"
    ).status_code == 401
    forbidden = client.post(
        f"/api/v1/intake-coordination/sessions/{session['id']}/review",
        headers=auth("b"),
        json={"action": "record_handoff", "reference": "FOREIGN-0007"},
    )
    assert forbidden.status_code == 404


def test_revoked_consent_blocks_inflight_staff_answer_and_handoff(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    session = _staff_session(client, admin, case["id"])
    withdrawal = client.post(
        "/api/v1/consents", headers=admin,
        json={"patient_id": patient["id"], "purpose": "intake",
              "accepted": False, "notice_version": "v7"},
    )
    assert withdrawal.status_code == 201
    assert client.post(
        f"/api/v1/intake/sessions/{session['id']}/answer",
        headers=admin, json={"answer": "Synthetic response"},
    ).status_code == 409
    assert client.get(
        f"/api/v1/intake/sessions/{session['id']}",
        headers=admin,
    ).status_code == 409
    assert client.post(
        "/api/v1/intake/sessions", headers=admin,
        json={"case_id": case["id"], "language": "en"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/intake-coordination/sessions/{session['id']}/review",
        headers=admin,
        json={"action": "record_handoff", "reference": "BLOCKED-0007"},
    ).status_code == 409


def test_blank_answers_rejected_and_stage_does_not_advance(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    session = _staff_session(client, admin, case["id"])
    for answer in (" ", "\n\t"):
        assert client.post(
            f"/api/v1/intake/sessions/{session['id']}/answer",
            headers=admin, json={"answer": answer},
        ).status_code == 422
    state = client.get(
        f"/api/v1/intake/sessions/{session['id']}", headers=admin
    ).json()
    assert state["stage"] == 0
