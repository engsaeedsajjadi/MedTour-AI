"""Synthetic Section 07 safety/clinical-handoff regression.

No credential or review here grants independent physician certification or
authorizes use of real patient information.
"""
from datetime import datetime, timedelta, timezone

from app.models import User
from app.security import password_hash
from app.enterprise_models import (
    IntakeReviewRecord, IntakeReviewerAssignment, ReviewerCredential
)


def setup_reviewer(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    with Session() as db:
        reviewer = User(
            tenant_id=tids[0],
            email="reviewer07@example.test",
            password_hash=password_hash("synthetic_reviewer_password123"),
            role="physician",
        )
        db.add(reviewer)
        db.commit()
        reviewer_id = reviewer.id
    access = auth("a", "reviewer07@example.test") if False else None
    # The fixture authenticates a fixed test password, so update the
    # synthetic physician's credentials to that password.
    with Session() as db:
        p = db.get(User, reviewer_id)
        p.password_hash = password_hash("test_password_12345")
        db.commit()
    physician = auth("a", "reviewer07@example.test")
    return client, auth, tids, Session, admin, patient, case, reviewer_id, physician


def submitted(client, admin, case_id):
    started = client.post("/api/v1/intake/sessions", headers=admin, json={
        "case_id": case_id, "language": "en",
    })
    assert started.status_code == 201, started.text
    sid = started.json()["id"]
    for i in range(5):
        r = client.post(
            f"/api/v1/intake/sessions/{sid}/answer",
            headers=admin, json={"answer": f"Synthetic test answer {i}"},
        )
        assert r.status_code == 200, r.text
    return sid


def register(client, admin, reviewer_id):
    r = client.put(
        f"/api/v1/intake-review/reviewers/{reviewer_id}/credential",
        headers=admin,
        json={
            "issuing_country": "IR", "issuing_authority": "Synthetic test registrar",
            "verification_reference": "SYNTHETIC-LIC-07",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=120)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["externally_verified"] is False
    return r


def test_physician_must_have_current_credential_and_case_assignment(seeded):
    client, auth, tids, Session, admin, patient, case, rid, physician = setup_reviewer(seeded)
    sid = submitted(client, admin, case["id"])
    endpoint = f"/api/v1/intake-review/sessions/{sid}/recommendation"
    payload = {"action": "external_clinical_assessment_required", "reference": "HANDOFF-CLINIC-07"}
    assert client.post(endpoint, json=payload).status_code == 401
    assert client.post(endpoint, headers=admin, json=payload).status_code == 403
    assert client.post(endpoint, headers=physician, json=payload).status_code == 403
    register(client, admin, rid)
    assert client.post(endpoint, headers=physician, json=payload).status_code == 403
    assigned = client.post(
        f"/api/v1/intake-review/sessions/{sid}/assignment",
        headers=admin, json={"reviewer_user_id": rid},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["clinical_approval"] is False
    item = client.post(endpoint, headers=physician, json=payload)
    assert item.status_code == 200, item.text
    assert item.json()["clinical_decision"] is False
    assert item.json()["independent_credential_verified"] is False
    assert item.json()["treatment_approved"] is False
    assert client.post(endpoint, headers=physician, json=payload).json()["created"] is False
    mine = client.get("/api/v1/intake-review/my-assignments", headers=physician)
    assert mine.status_code == 200
    assert mine.json()["items"][0]["session_id"] == sid
    assert mine.json()["raw_medical_answers_included"] is False
    events = client.get(
        f"/api/v1/intake-review/sessions/{sid}/events", headers=physician
    )
    assert events.status_code == 200
    assert len(events.json()["records"]) == 1
    assert "SYNTHETIC-LIC-07" not in str(events.json())
    assert "Synthetic test answer" not in str(events.json())
    with Session() as db:
        assert db.query(IntakeReviewRecord).count() == 1
        assert db.query(ReviewerCredential).count() == 1
        assert db.query(IntakeReviewerAssignment).count() == 1


def test_other_tenant_cannot_attest_assign_or_view(seeded):
    client, auth, tids, Session, admin, patient, case, rid, physician = setup_reviewer(seeded)
    sid = submitted(client, admin, case["id"])
    assert client.put(
        f"/api/v1/intake-review/reviewers/{rid}/credential",
        headers=auth("b"), json={
            "issuing_country": "IR", "issuing_authority": "Fake office",
            "verification_reference": "FOREIGN-0007",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=180)).isoformat(),
        },
    ).status_code == 404
    assert client.post(
        f"/api/v1/intake-review/sessions/{sid}/assignment",
        headers=auth("b"), json={"reviewer_user_id": rid}
    ).status_code == 404
    assert client.get(
        f"/api/v1/intake-review/sessions/{sid}/events",
        headers=auth("b"),
    ).status_code == 404


def test_urgent_escalation_is_never_automatically_cleared(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    start = client.post("/api/v1/intake/sessions", headers=admin, json={
        "case_id": case["id"], "language": "en"
    }).json()
    sid = start["id"]
    emergency = client.post(
        f"/api/v1/intake/sessions/{sid}/answer",
        headers=admin, json={"answer": "I have severe bleeding"},
    )
    assert emergency.status_code == 200
    url = f"/api/v1/intake-review/sessions/{sid}/escalation"
    payload = {"action": "urgent_alert_acknowledged", "reference": "STAFF-RECEIVED-07"}
    first = client.post(url, headers=admin, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["urgent_alert_active"]
    assert not first.json()["contact_success_confirmed"]
    second = client.post(url, headers=admin, json=payload)
    assert second.status_code == 200 and second.json()["created"] is False
    third = client.post(url, headers=auth("a", "operator@example.test"), json={
        "action": "external_contact_attempt_recorded", "reference": "DIAL-EXTERNAL-07"
    })
    assert third.status_code == 200, third.text
    assert not third.json()["automated_clearance"]
    status = client.get(f"/api/v1/intake-coordination/cases/{case['id']}",headers=admin)
    assert status.status_code == 200
    assert status.json()["urgency_keyword_alert"] is True
    mission = client.get(f"/api/v1/cases/{case['id']}/mission",headers=admin).json()
    assert mission["conditions"]["emergency_clear"] is False
    assert client.post(
        f"/api/v1/intake-coordination/sessions/{sid}/review",
        headers=admin, json={"action": "record_handoff", "reference": "DONT-CLEAR-07"}
    ).status_code == 409
    policy = client.get("/api/v1/intake-review/escalation-policy", headers=admin)
    assert policy.status_code == 200
    assert not policy.json()["clinical_triage_validated"]
    assert not policy.json()["automatic_alert_clearance"]
    with Session() as db:
        assert db.query(IntakeReviewRecord).count() == 2


def test_revoked_consent_prevents_review_and_assignment(seeded):
    client, auth, tids, Session, admin, patient, case, rid, physician = setup_reviewer(seeded)
    sid = submitted(client, admin, case["id"])
    register(client, admin, rid)
    assert client.post(
        f"/api/v1/intake-review/sessions/{sid}/assignment",
        headers=admin, json={"reviewer_user_id": rid}
    ).status_code == 200
    withdrew = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "intake",
        "accepted": False, "notice_version": "v-review-revoked"
    })
    assert withdrew.status_code == 201
    assert client.post(
        f"/api/v1/intake-review/sessions/{sid}/recommendation",
        headers=physician, json={
            "action": "additional_information_requested",
            "reference": "REVOKED-0007",
        }
    ).status_code == 409
    assert client.get(
        "/api/v1/intake-review/my-assignments", headers=physician
    ).json()["items"] == []


def test_metadata_validation_blocks_unverified_credentials_and_diagnosis(seeded):
    client, auth, tids, Session, admin, patient, case, rid, physician = setup_reviewer(seeded)
    sid = submitted(client, admin, case["id"])
    url = f"/api/v1/intake-review/reviewers/{rid}/credential"
    bad = {"issuing_country": "IR", "issuing_authority": "Synthetic",
           "verification_reference": "REF-00007"}
    assert client.put(url, headers=admin, json={
        **bad, "expires_at": "2026-01-01T00:00:00+00:00"
    }).status_code == 422
    assert client.put(url, headers=admin, json={
        **bad, "expires_at": (datetime.now(timezone.utc) + timedelta(days=120)).replace(tzinfo=None).isoformat()
    }).status_code == 422
    register(client, admin, rid)
    assert client.post(
        f"/api/v1/intake-review/sessions/{sid}/assignment",
        headers=admin, json={"reviewer_user_id": rid}
    ).status_code == 200
    for invalid in ("approve_treatment", "diagnose", "clear_urgent_alert"):
        r=client.post(
            f"/api/v1/intake-review/sessions/{sid}/recommendation",
            headers=physician, json={"action": invalid, "reference": "TEST-SAFE-0007"}
        )
        assert r.status_code == 422
    assert client.post(
        f"/api/v1/intake-review/sessions/{sid}/recommendation",
        headers=physician,
        json={"action": "additional_information_requested", "reference": "PHI patient name"}
    ).status_code == 422
