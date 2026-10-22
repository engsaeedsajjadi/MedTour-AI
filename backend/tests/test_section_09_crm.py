"""Section 09 CRM safety tests using synthetic patients and no provider traffic."""
from datetime import datetime, timedelta, timezone

from app.enterprise_models import CRMFollowUp, CRMDuplicateReview, CaseTimeline
from app.models import Patient


def _consent(client, admin, patient_id, accepted=True):
    response=client.post("/api/v1/consents", headers=admin, json={
        "patient_id":patient_id, "purpose":"communication",
        "accepted":accepted, "notice_version":"section09",
    })
    assert response.status_code==201, response.text


def _schedule(client, admin, case_id, assignee, key="crm-fixture-0001", minutes=30):
    return client.post("/api/v1/crm/followups",headers=admin,json={
        "case_id":case_id, "assigned_user_id":assignee,
        "idempotency_key":key, "reason_code":"appointment_coordination",
        "due_at":(datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat(),
    })


def test_crm_followup_schedule_idempotency_and_completion(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    _consent(client,admin,patient["id"])
    user_id=client.get("/api/v1/auth/me",headers=admin).json()["id"]
    created=_schedule(client,admin,case["id"],user_id)
    assert created.status_code==201,created.text
    body=created.json()
    assert body["status"]=="open" and not body["reused"]
    assert body["automated_send"] is False
    # Use the original due date rather than generating a different timestamp.
    duplicate=client.post("/api/v1/crm/followups",headers=admin,json={
        "case_id":case["id"],"assigned_user_id":user_id,
        "idempotency_key":"crm-fixture-0001","reason_code":"appointment_coordination",
        "due_at":body["due_at"],
    })
    assert duplicate.status_code==201,duplicate.text
    assert duplicate.json()["reused"]
    assert duplicate.json()["id"]==body["id"]
    wrong=client.post("/api/v1/crm/followups",headers=admin,json={
        "case_id":case["id"],"assigned_user_id":user_id,
        "idempotency_key":"crm-fixture-0001","reason_code":"check_in",
        "due_at":body["due_at"],
    })
    assert wrong.status_code==409
    result=client.post(f"/api/v1/crm/followups/{body['id']}/resolve",
        headers=admin,json={"action":"complete",
        "outcome_code":"human_contact_completed","reference":"CONTACT-CRM-09"})
    assert result.status_code==200,result.text
    assert result.json()["status"]=="completed"
    assert result.json()["contact_verified_externally"] is False
    assert "CONTACT-CRM-09" not in str(client.get(
        "/api/v1/crm/followups",headers=admin).json())
    assert client.post(f"/api/v1/crm/followups/{body['id']}/resolve",
        headers=admin,json={"action":"complete",
        "outcome_code":"human_contact_completed","reference":"CONTACT-CRM-09"}).status_code==409
    with Session() as db:
        assert db.query(CRMFollowUp).count()==1
        assert db.query(CaseTimeline).filter(CaseTimeline.event=="crm_followup_completed").count()==1


def test_crm_consent_withdrawal_blocks_pending_and_regrant_does_not_reopen(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    user_id=client.get("/api/v1/auth/me",headers=admin).json()["id"]
    assert _schedule(client,admin,case["id"],user_id).status_code==409
    _consent(client,admin,patient["id"])
    first=_schedule(client,admin,case["id"],user_id).json()
    _consent(client,admin,patient["id"],False)
    with Session() as db:
        row=db.get(CRMFollowUp,first["id"])
        assert row.status=="blocked"
    assert client.post(f"/api/v1/crm/followups/{first['id']}/resolve",
        headers=admin,json={"action":"complete",
        "outcome_code":"contact_attempted","reference":"NO-CONSENT-09"}).status_code==409
    _consent(client,admin,patient["id"])
    assert client.get("/api/v1/crm/followups?status=open",headers=admin).json()["items"]==[]
    assert _schedule(client,admin,case["id"],user_id,key="crm-fixture-0002").status_code==201


def test_duplicate_contact_candidates_are_tenant_scoped_and_non_destructive(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    with Session() as db:
        original=db.get(Patient,patient["id"])
        original.contact="+44 7700 900123"
        db.commit()
    second=client.post("/api/v1/patients",headers=admin,json={
        "full_name":"Another synthetic person","contact":"447700900123","language":"ar"
    })
    assert second.status_code==201,second.text
    ident=second.json()["id"]
    candidate_path=f"/api/v1/crm/patients/{patient['id']}/duplicates"
    assert client.get(candidate_path).status_code==401
    assert client.get(candidate_path,headers=auth("a","operator@example.test")).status_code==403
    assert client.get(candidate_path,headers=auth("b")).status_code==404
    found=client.get(candidate_path,headers=admin)
    assert found.status_code==200,found.text
    assert found.json()["candidates"]==[{"patient_id":ident,"basis":"exact_normalized_contact"}]
    assert not found.json()["identity_verified"] and not found.json()["automatic_merge"]
    reviewed=client.post(f"/api/v1/crm/patients/{patient['id']}/duplicate-review",
        headers=admin,json={"candidate_patient_id":ident,
                            "decision":"possible_same","reference":"HUMAN-REVIEW-09"})
    assert reviewed.status_code==200,reviewed.text
    assert not reviewed.json()["patient_records_merged"]
    assert not reviewed.json()["clinical_identity_verified"]
    reverse=client.post(f"/api/v1/crm/patients/{ident}/duplicate-review",
        headers=admin,json={"candidate_patient_id":patient["id"],
                            "decision":"possible_same","reference":"HUMAN-REVIEW-09"})
    assert reverse.status_code==200 and reverse.json()["reused"] is True
    assert client.post(f"/api/v1/crm/patients/{ident}/duplicate-review",
        headers=admin,json={"candidate_patient_id":patient["id"],
                            "decision":"distinct","reference":"DIFFERENT-09"}).status_code==409
    with Session() as db:
        assert db.query(Patient).filter(Patient.tenant_id==tids[0]).count()==2
        assert db.query(CRMDuplicateReview).count()==1


def test_duplicate_review_rejects_unmatched_and_other_tenant_patients(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    other=client.post("/api/v1/patients",headers=admin,json={
        "full_name":"Third synthetic patient","contact":"123456789012"
    }).json()
    endpoint=f"/api/v1/crm/patients/{patient['id']}/duplicate-review"
    assert client.post(endpoint,headers=admin,json={
        "candidate_patient_id":other["id"],"decision":"possible_same",
        "reference":"NO-MATCH-09"}).status_code==409
    assert client.post(endpoint,headers=admin,json={
        "candidate_patient_id":patient["id"],"decision":"possible_same",
        "reference":"SELF-CHECK-09"}).status_code==422
    assert client.post(endpoint,headers=auth("b"),json={
        "candidate_patient_id":other["id"],"decision":"possible_same",
        "reference":"FOREIGN-09"}).status_code==404


def test_followup_assignee_owner_guard_and_tenant_scope(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    _consent(client,admin,patient["id"])
    op_header=auth("a","operator@example.test")
    admin_id=client.get("/api/v1/auth/me",headers=admin).json()["id"]
    op_id=client.get("/api/v1/auth/me",headers=op_header).json()["id"]
    assert client.post(f"/api/v1/crm/cases/{case['id']}/assign",
        headers=op_header,json={"coordinator_user_id":op_id}).status_code==403
    assigned=client.post(f"/api/v1/crm/cases/{case['id']}/assign",
        headers=admin,json={"coordinator_user_id":op_id})
    assert assigned.status_code==200,assigned.text
    assert assigned.json()["coordinator_user_id"]==op_id
    assert client.post(f"/api/v1/crm/patients/{patient['id']}/assign",
        headers=admin,json={"coordinator_user_id":op_id}).status_code==200
    assert client.post(f"/api/v1/crm/cases/{case['id']}/assign",
        headers=auth("b"),json={"coordinator_user_id":op_id}).status_code==404
    assert client.post(f"/api/v1/crm/cases/{case['id']}/assign",
        headers=admin,json={"coordinator_user_id":client.get(
            "/api/v1/auth/me",headers=auth("b")).json()["id"]}).status_code==404
    item=_schedule(client,admin,case["id"],op_id).json()
    assert client.get("/api/v1/crm/followups",headers=op_header).json()["items"][0]["id"]==item["id"]
    assert client.get("/api/v1/crm/followups",headers=auth("b")).json()["items"]==[]
    assert client.post(f"/api/v1/crm/followups/{item['id']}/resolve",
        headers=auth("b"),json={"action":"cancel"}).status_code==404
    assert client.post(f"/api/v1/crm/followups/{item['id']}/resolve",
        headers=op_header,json={"action":"cancel"}).status_code==200


def test_crm_overview_excludes_sensitive_data_and_no_outreach(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    result=client.get(f"/api/v1/crm/patients/{patient['id']}/overview",headers=admin)
    assert result.status_code==200,result.text
    x=result.json()
    assert x["cases"][0]["id"]==case["id"]
    assert x["no_medical_notes_included"] is True
    assert x["automatic_outreach_enabled"] is False
    assert "complaint" not in str(x)
    assert "contact" not in str(x["cases"])
    assert client.get(f"/api/v1/crm/patients/{patient['id']}/overview",
                      headers=auth("b")).status_code==404


def test_followup_validation_requires_tz_reference_and_valid_user(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    _consent(client,admin,patient["id"])
    admin_id=client.get("/api/v1/auth/me",headers=admin).json()["id"]
    url="/api/v1/crm/followups"
    payload={"case_id":case["id"],"assigned_user_id":admin_id,
             "reason_code":"general_administrative",
             "due_at":"2026-10-23T17:00:00",
             "idempotency_key":"crm-validation-09"}
    assert client.post(url,headers=admin,json=payload).status_code==422
    response=client.post(url,headers=admin,json={**payload,
        "due_at":(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
        "assigned_user_id":"absent-user"})
    assert response.status_code==404
