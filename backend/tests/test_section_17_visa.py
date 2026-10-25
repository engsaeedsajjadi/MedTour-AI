"""Section 17 synthetic visa workflow, consent and tenant-security regressions."""
from datetime import datetime, timedelta, timezone
from app.enterprise_models import MedicalVisa, MedicalVisaChecklist, MedicalVisaEvent

ROOT = "/api/v1/visa-coordination"
REF = "SYNTHETIC-ADMIN-REF-17"


def allow(client, admin, patient_id):
    response = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient_id, "purpose": "visa_coordination",
        "accepted": True, "notice_version": "v17-synthetic"})
    assert response.status_code == 201, response.text


def new(client, admin, case_id, key="VISA-SYNTH-REQUEST-17", **changes):
    payload = {"request_key": key, "origin_country": "AF",
               "destination_country": "IR", "visa_type": "medical", **changes}
    return client.post(ROOT + "/cases/" + case_id + "/applications",
                       headers=admin, json=payload)


def step(client, user, id, action, key, **extra):
    return client.post(ROOT + "/applications/" + id + "/transition",
        headers=user, json={"step_key": key, "action": action,
                            "reference": REF, **extra})


def test_full_internal_review_manual_submission_outcome_and_history(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    assert new(client, admin, case["id"]).status_code == 409
    allow(client, admin, patient["id"])
    response = new(client, admin, case["id"])
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["reused"] is False
    assert row["official_visa_issued_verified"] is False
    assert row["government_integration_live"] is False
    assert len(row["checklist"]) == 4
    ident = row["id"]
    dup = new(client, admin, case["id"])
    assert dup.status_code == 201 and dup.json()["reused"] is True
    assert new(client, admin, case["id"], origin_country="IQ").status_code == 409
    operator = auth("a", "operator@example.test")
    assert step(client, operator, ident, "start_review", "STEP-START-VISA-17").status_code == 200
    early = step(client, admin, ident, "ready_for_manual_submission", "STEP-EARLY-VISA-17")
    assert early.status_code == 409
    assert client.post(ROOT + "/applications/" + ident + "/checklist",
        headers=operator, json={"item_key": "identity_document",
           "status": "locally_reviewed", "review_reference": REF}).status_code == 403
    for key in ("identity_document", "provider_invitation", "travel_plan", "application_forms"):
        reply = client.post(ROOT + "/applications/" + ident + "/checklist",
            headers=admin, json={"item_key": key, "status": "locally_reviewed",
                                 "review_reference": "LOCAL-" + REF})
        assert reply.status_code == 200, reply.text
    assert step(client, operator, ident, "ready_for_manual_submission",
                "STEP-BY-OPERATOR-17").status_code == 403
    ready = step(client, admin, ident, "ready_for_manual_submission", "STEP-READY-VISA-17")
    assert ready.status_code == 200 and ready.json()["status"] == "ready_for_manual_submission"
    assert step(client, admin, ident, "record_submission", "STEP-NO-AUTH-17").status_code == 422
    submit = step(client, admin, ident, "record_submission",
                  "STEP-SUBMITTED-VISA-17", authority_name="Synthetic Desk")
    assert submit.status_code == 200 and submit.json()["status"] == "submission_reported"
    replay = step(client, admin, ident, "record_submission",
                  "STEP-SUBMITTED-VISA-17", authority_name="Synthetic Desk")
    assert replay.status_code == 200 and replay.json()["reused"] is True
    assert step(client, admin, ident, "record_submission",
                "STEP-SUBMITTED-VISA-17", authority_name="Different Desk").status_code == 409
    wrong = step(client, admin, ident, "record_outcome", "STEP-NO-OUTCOME-17",
                 authority_name="Synthetic Desk")
    assert wrong.status_code == 422
    outcome = step(client, admin, ident, "record_outcome", "STEP-OUTCOME-VISA-17",
                   authority_name="Synthetic Desk", outcome="issued_reported")
    assert outcome.status_code == 200 and outcome.json()["status"] == "outcome_reported"
    assert outcome.json()["official_visa_issued_verified"] is False
    history = client.get(ROOT + "/applications/" + ident + "/history", headers=admin)
    assert history.status_code == 200 and len(history.json()["items"]) == 4
    assert history.json()["independent_authority_verification"] is False
    assert step(client, admin, ident, "cancel", "STEP-CANCEL-ISSUED-17").status_code == 409
    with Session() as db:
        assert db.query(MedicalVisa).count() == 1
        assert db.query(MedicalVisaChecklist).count() == 4
        assert db.query(MedicalVisaEvent).count() == 4


def test_consent_withdrawal_blocks_old_request_permanently(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    allow(client, admin, patient["id"])
    ident = new(client, admin, case["id"]).json()["id"]
    assert step(client, admin, ident, "start_review", "STEP-START-WITHDRAW-17").status_code == 200
    # Patient-attested link withdrawal shares the same revocation hook as staff withdrawal.
    token = client.post("/api/v1/consent-links/" + patient["id"] + "/visa_coordination",
                        headers=admin).json()["token"]
    reject = client.post("/api/v1/consent-links/respond", json={
        "token": token, "notice_version": "v17-synthetic", "accepted": False})
    assert reject.status_code == 201, reject.text
    assert client.get(ROOT + "/cases/" + case["id"] + "/applications",
                      headers=admin).status_code == 409
    with Session() as db:
        row = db.query(MedicalVisa).filter(MedicalVisa.id == ident).one()
        assert row.status == "blocked"
    allow(client, admin, patient["id"])
    listed = client.get(ROOT + "/cases/" + case["id"] + "/applications", headers=admin)
    assert listed.status_code == 200 and listed.json()["items"][0]["status"] == "blocked"
    assert step(client, admin, ident, "start_review", "STEP-REOPEN-VISA-17").status_code == 409
    assert new(client, admin, case["id"]).status_code == 409
    fresh = new(client, admin, case["id"], key="VISA-FRESH-REQUEST-17")
    assert fresh.status_code == 201 and fresh.json()["id"] != ident


def test_consent_and_country_validation_and_no_legacy_visa_shortcut(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    assert new(client, admin, case["id"], origin_country="Af").status_code == 422
    allow(client, admin, patient["id"])
    assert new(client, admin, case["id"], destination_country="US").status_code == 422
    invalid_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert new(client, admin, case["id"], intended_departure_at=invalid_date).status_code == 422
    legacy = client.post("/api/v1/travel", headers=admin, json={
        "case_id": case["id"], "service_type": "visa", "notes": "synthetic generic request"})
    assert legacy.status_code == 201
    no_reference = client.patch("/api/v1/travel/" + legacy.json()["id"] + "/status",
        headers=admin, json={"status": "confirmed"})
    assert no_reference.status_code == 422
    blocked = client.patch("/api/v1/travel/" + legacy.json()["id"] + "/status",
        headers=admin, json={"status": "confirmed", "reference": REF})
    assert blocked.status_code == 409
    # No passport number, medical narrative, or arbitrary attachments in typed request.
    assert "passport_number" not in new(client, admin, case["id"],
      key="VISA-SECOND-REQUEST-17", passport_number="SECRET").json()


def test_tenant_boundary_and_intake_withdrawal(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    allow(client, admin, patient["id"])
    item = new(client, admin, case["id"]).json()
    outsider = auth("b")
    assert client.get(ROOT + "/cases/" + case["id"] + "/applications", headers=outsider).status_code == 404
    assert client.post(ROOT + "/cases/" + case["id"] + "/applications",
            headers=outsider, json={"request_key": "FOREIGN-CREATE-VISA-17",
                                   "origin_country": "AF"}).status_code == 404
    assert client.get(ROOT + "/applications/" + item["id"] + "/history",
                      headers=outsider).status_code == 404
    assert step(client, outsider, item["id"], "start_review",
                "FOREIGN-TRANSITION-17").status_code == 404
    revoke = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "intake",
        "accepted": False, "notice_version": "v17-synthetic"})
    assert revoke.status_code == 201
    with Session() as db:
        assert db.query(MedicalVisa).filter(MedicalVisa.id == item["id"]).one().status == "blocked"


def test_due_queue_is_bounded_and_only_returns_authorized_cases(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    allow(client, admin, patient["id"])
    due_at = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    record = new(client, admin, case["id"], next_action_due_at=due_at)
    assert record.status_code == 201, record.text
    from app.enterprise_models import MedicalVisa
    with Session() as db:
        row = db.query(MedicalVisa).filter(MedicalVisa.id == record.json()["id"]).one()
        row.next_action_due_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        db.commit()
    result = client.get(ROOT + "/due", headers=admin)
    assert result.status_code == 200 and len(result.json()["items"]) == 1
    assert result.json()["automatic_notifications_sent"] is False
    assert client.get(ROOT + "/due", headers=auth("b")).json()["items"] == []
