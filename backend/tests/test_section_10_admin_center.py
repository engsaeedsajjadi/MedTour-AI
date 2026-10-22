"""Section 10 administrator-only controls; synthetic data, never real PHI."""
from datetime import datetime, timedelta, timezone

from app.models import Patient, Case, Audit, User
from app.enterprise_models import Operation, CRMFollowUp


ROOT = "/api/v1/admin-center"


def _my_id(client, headers):
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def _communication(client, headers, patient_id):
    r = client.post("/api/v1/consents", headers=headers, json={
        "patient_id": patient_id, "purpose": "communication",
        "accepted": True, "notice_version": "synthetic-v10",
    })
    assert r.status_code == 201


def test_control_center_is_admin_only_and_tenant_scoped(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    op = auth("a", "operator@example.test")
    for endpoint in ("/summary", "/queue", "/search?q=synthetic",
                     f"/cases/{case['id']}/overview"):
        assert client.get(ROOT + endpoint).status_code == 401
        assert client.get(ROOT + endpoint, headers=op).status_code == 403
    across = client.get(ROOT + f"/cases/{case['id']}/overview", headers=auth("b"))
    assert across.status_code == 404
    summary = client.get(ROOT + "/summary", headers=admin)
    assert summary.status_code == 200, summary.text
    assert summary.json()["patients"] == 1
    assert summary.json()["cases"] == 1
    assert summary.json()["metrics_source"] == "tenant_database"
    assert summary.json()["external_providers_live_verified"] is False
    assert client.get(ROOT + "/summary", headers=auth("b")).json()["cases"] == 0


def test_search_does_not_disclose_contact_complaint_or_operational_notes(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    with Session() as db:
        p = db.get(Patient, patient["id"])
        p.contact = "PRIVATE_CONTACT_999999"
        c = db.get(Case, case["id"])
        c.complaint = "PRIVATE_CLINICAL_DETAIL_999"
        db.commit()
    op = client.post("/api/v1/operations", headers=admin, json={
        "kind": "visa", "case_id": case["id"],
        "title": "PRIVATE_OPERATION_NOTE_999",
        "metadata": {"medical_record": "SECRET_MEDICAL_VALUE_999"},
    })
    assert op.status_code == 201, op.text
    patients = client.get(ROOT + "/search?q=Synthetic&domain=patients", headers=admin)
    assert patients.status_code == 200
    assert patients.json()["items"][0]["type"] == "patient"
    cases = client.get(ROOT + "/search?q=new&domain=cases", headers=admin)
    assert cases.status_code == 200
    assert cases.json()["items"][0]["case_id"] == case["id"]
    operations = client.get(ROOT + "/search?q=visa&domain=operations", headers=admin)
    assert operations.status_code == 200
    assert operations.json()["items"][0]["id"] == op.json()["id"]
    combined = str([patients.json(), cases.json(), operations.json()])
    assert all(secret not in combined for secret in (
        "PRIVATE_CONTACT", "PRIVATE_CLINICAL", "PRIVATE_OPERATION", "SECRET_MEDICAL"
    ))
    assert client.get(ROOT + "/search?q=ab", headers=admin).status_code == 422
    assert client.get(ROOT + "/search?q=   ", headers=admin).status_code == 422
    assert client.get(ROOT + "/search?q=visa&domain=unknown", headers=admin).status_code == 422
    assert client.get(ROOT + "/search?q=visa", headers=auth("b")).json()["items"] == []


def test_queue_surfaces_urgent_intake_and_never_clears_it(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    started = client.post("/api/v1/intake/sessions", headers=admin, json={
        "case_id": case["id"], "language": "en",
    })
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]
    sent = client.post(f"/api/v1/intake/sessions/{session_id}/answer",
                       headers=admin, json={"answer": "I have severe bleeding"})
    assert sent.status_code == 200
    queue = client.get(ROOT + "/queue", headers=admin)
    assert queue.status_code == 200, queue.text
    item = next(x for x in queue.json()["items"] if x["category"] == "urgent_intake")
    assert item["case_id"] == case["id"]
    assert item["priority"] == "urgent"
    assert item["destination"] == "/intake-review"
    assert item["automatic_decision"] is False
    assert queue.json()["total_matches_exhaustive"] is False
    assert queue.json()["medical_content_included"] is False
    assert "severe bleeding" not in str(queue.json())
    second = client.get(ROOT + "/queue?category=urgent_intake&limit=1", headers=admin)
    assert len(second.json()["items"]) == 1
    assert second.json()["items"][0]["id"] == item["id"]
    assert client.get(ROOT + f"/cases/{case['id']}/overview", headers=admin
                      ).json()["clinical_review_approved"] is False


def test_queue_and_summary_reflect_real_followups_ops_and_quotes(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    _communication(client, admin, patient["id"])
    user_id = _my_id(client, admin)
    followup = client.post("/api/v1/crm/followups", headers=admin, json={
        "case_id": case["id"], "assigned_user_id": user_id,
        "idempotency_key": "section10-overdue-0001",
        "reason_code": "check_in",
        "due_at": (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
    })
    assert followup.status_code == 201, followup.text
    operation = client.post("/api/v1/operations", headers=admin, json={
        "kind": "transport", "case_id": case["id"], "title": "Synthetic transport",
        "metadata": {},
    })
    assert operation.status_code == 201, operation.text
    quote = client.post("/api/v1/quotes", headers=admin, json={
        "case_id": case["id"], "currency": "USD", "amount_minor": 1200,
        "details": "synthetic draft",
    })
    assert quote.status_code == 201, quote.text
    summary = client.get(ROOT + "/summary", headers=admin).json()
    assert summary["overdue_followups"] == 1
    assert summary["pending_operations"] == 1
    assert summary["draft_quotes"] == 1
    queue = client.get(ROOT + "/queue", headers=admin).json()["items"]
    assert {x["category"] for x in queue} >= {
        "followup_overdue", "operation_review", "quote_approval"
    }
    assert queue[0]["category"] == "followup_overdue"
    case_view = client.get(ROOT + f"/cases/{case['id']}/overview", headers=admin)
    assert case_view.status_code == 200
    assert case_view.json()["open_followups"] == 1
    assert case_view.json()["pending_operations"] == 1
    assert "synthetic draft" not in str(case_view.json())


def test_guarded_user_deactivation_reassign_and_token_revocation(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    op_headers = auth("a", "operator@example.test")
    op_id = _my_id(client, op_headers)
    admin_id = _my_id(client, admin)
    assert client.post(ROOT + f"/staff/{op_id}/deactivate", headers=op_headers).status_code == 403
    assert client.post(ROOT + f"/staff/{admin_id}/deactivate", headers=admin).status_code == 409
    assign = client.post(f"/api/v1/crm/cases/{case['id']}/assign", headers=admin,
                         json={"coordinator_user_id": op_id})
    assert assign.status_code == 200
    assert client.post(ROOT + f"/staff/{op_id}/deactivate", headers=admin).status_code == 409
    assign_back = client.post(f"/api/v1/crm/cases/{case['id']}/assign", headers=admin,
                              json={"coordinator_user_id": admin_id})
    assert assign_back.status_code == 200
    stopped = client.post(ROOT + f"/staff/{op_id}/deactivate", headers=admin)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["active"] is False
    assert client.post(ROOT + f"/staff/{op_id}/deactivate", headers=admin).json()["reused"]
    assert client.get("/api/v1/cases", headers=op_headers).status_code == 401
    failed_login = client.post("/api/v1/auth/login", json={
        "tenant_slug": "a", "email": "operator@example.test",
        "password": "test_password_12345",
    })
    assert failed_login.status_code == 401
    with Session() as db:
        row = db.get(User, op_id)
        assert row.active is False
        assert db.query(Audit).filter(
            Audit.event == "admin_center_staff_deactivated",
            Audit.entity_id == op_id,
        ).count() == 1
    assert client.post(ROOT + f"/staff/{op_id}/deactivate",
                       headers=auth("b")).status_code == 404


def test_staff_work_must_be_resolved_before_deactivation(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    op_id = _my_id(client, auth("a", "operator@example.test"))
    _communication(client, admin, patient["id"])
    followup = client.post("/api/v1/crm/followups", headers=admin, json={
        "case_id": case["id"], "assigned_user_id": op_id,
        "idempotency_key": "section10-reassignment-0001", "reason_code": "check_in",
        "due_at": (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
    })
    assert followup.status_code == 201
    assert client.post(ROOT + f"/staff/{op_id}/deactivate",
                       headers=admin).status_code == 409
    cancelled = client.post(
        "/api/v1/crm/followups/" + followup.json()["id"] + "/resolve",
        headers=admin, json={"action": "cancel"},
    )
    assert cancelled.status_code == 200
    assert client.post(ROOT + f"/staff/{op_id}/deactivate",
                       headers=admin).status_code == 200
