"""Synthetic integrated-module regression. Does not create any real medical data."""
from app.models import User
from app.security import password_hash


def test_module_catalog_requires_staff_and_is_truthful(context):
    client, auth, _, Session = context
    assert client.get("/api/v1/modules").status_code == 401
    a = auth("a")
    response = client.get("/api/v1/modules", headers=a)
    assert response.status_code == 200
    body = response.json()
    keys = {x["key"] for x in body["modules"]}
    assert {"patients", "cases", "intake", "documents",
            "physicians", "appointments", "quotes", "travel",
            "services", "conversations", "subscriptions", "voice"}.issubset(keys)
    assert len(keys) == len(body["modules"])
    assert body["production_ready"] is False
    assert body["external_services_verified"] is False
    assert next(x for x in body["modules"] if x["key"] == "voice")["status"] == "not_delivered"
    assert next(x for x in body["modules"] if x["key"] == "travel")["status"] == "external_gate"


def test_case_workspace_uses_tenant_and_case_filters(seeded):
    (client, auth, _, _), admin, patient, case = seeded
    url = "/api/v1/modules/cases/" + case["id"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth("b")).status_code == 404
    assert client.get(url, headers=admin).status_code == 200
    data = client.get(url, headers=admin).json()
    assert data["counts"]["appointments"] == 0
    assert data["counts"]["quotes"] == 0
    assert data["production_ready"] is False
    assert data["case_id"] == case["id"]
    assert "complaint" not in data and "patient_id" not in data
    assert "contact" not in data
    assert data["readiness"]["intake_consent"]

    second = client.post(
        "/api/v1/patients", headers=admin,
        json={"full_name": "Synthetic second patient", "language": "fa"}
    ).json()
    assert client.post(
        "/api/v1/consents", headers=admin,
        json={"patient_id": second["id"], "purpose": "intake",
              "accepted": True, "notice_version": "v2"}
    ).status_code == 201
    second_case = client.post(
        "/api/v1/cases", headers=admin, json={"patient_id": second["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks", headers=admin,
        json={"case_id": second_case["id"], "title": "Other-case-only task"}
    )
    assert task.status_code == 201
    assert client.get(url, headers=admin).json()["counts"]["tasks"] == 0

    own_task = client.post(
        "/api/v1/tasks", headers=admin,
        json={"case_id": case["id"], "title": "Synthetic SECRET MEDICAL NOTE should not echo"}
    )
    assert own_task.status_code == 201
    updated = client.get(url, headers=admin).json()
    assert updated["counts"]["tasks"] == 1
    assert updated["counts"]["tasks_open"] == 1
    assert updated["tasks"][0]["id"] == own_task.json()["id"]
    assert "SECRET MEDICAL NOTE" not in str(updated)
    assert "title" not in updated["tasks"][0]


def test_task_transition_scoped_audited_and_no_double_completion(seeded):
    (client, auth, _, Session), admin, patient, case = seeded
    task = client.post(
        "/api/v1/tasks", headers=admin,
        json={"case_id": case["id"], "title": "Synthetic appointment coordination"}
    ).json()
    base = "/api/v1/modules/cases/" + case["id"] + "/tasks/" + task["id"] + "/status"
    payload = {"status": "done", "reference": "TEST-CASE-43210"}
    assert client.patch(base, json=payload).status_code == 401
    assert client.patch(base, headers=auth("b"), json=payload).status_code == 404
    assert client.patch(base, headers=admin, json={"status":"done","reference":"x"}).status_code == 422
    operator = auth("a", "operator@example.test")
    completed = client.patch(base, headers=operator, json=payload)
    assert completed.status_code == 200, completed.text
    assert completed.json()["external_confirmation"] is False
    assert client.patch(base, headers=operator, json=payload).status_code == 409
    check = client.get("/api/v1/modules/cases/" + case["id"], headers=admin).json()
    assert check["counts"]["tasks_open"] == 0
    assert check["tasks"][0]["status"] == "done"
    assert client.patch(base, headers=admin, json={"status":"open","reference":"TEST-REOPEN-400"}).status_code == 200
    assert client.get("/api/v1/modules/cases/"+case["id"], headers=admin).json()["counts"]["tasks_open"] == 1
    audits = client.get("/api/v1/audit", headers=admin).json()
    assert len([e for e in audits if e["event"] == "case_task_state_changed"]) == 2


def test_cross_case_task_update_is_denied(seeded):
    (client, auth, _, _), admin, patient, case = seeded
    second_patient = client.post(
        "/api/v1/patients", headers=admin,
        json={"full_name": "Different synthetic patient"}
    ).json()
    client.post(
        "/api/v1/consents", headers=admin,
        json={"patient_id":second_patient["id"], "purpose":"intake",
              "accepted":True,"notice_version":"v1"}
    )
    second_case = client.post(
        "/api/v1/cases", headers=admin,
        json={"patient_id":second_patient["id"]}
    ).json()
    task = client.post(
        "/api/v1/tasks", headers=admin,
        json={"case_id": second_case["id"], "title": "Not my case task"}
    ).json()
    wrong = "/api/v1/modules/cases/"+case["id"]+"/tasks/"+task["id"]+"/status"
    response = client.patch(wrong, headers=admin,
                            json={"status":"done","reference":"TEST-CROSS-222"})
    assert response.status_code == 404


def test_summary_tenant_isolation_and_role(context):
    client, auth, _, Session = context
    a = auth("a")
    b = auth("b")
    assert client.get("/api/v1/modules/summary").status_code == 401
    a_pat = client.post("/api/v1/patients", headers=a,
                        json={"full_name":"Synthetic person a"}).json()
    count_a = client.get("/api/v1/modules/summary", headers=a)
    count_b = client.get("/api/v1/modules/summary", headers=b)
    assert count_a.status_code == count_b.status_code == 200
    assert count_a.json()["counts"]["patients"] == 1
    assert count_b.json()["counts"]["patients"] == 0
    assert count_a.json()["production_ready"] is False
    assert "full_name" not in count_a.json()
    with Session() as db:
        tenant = db.get(User, db.query(User).filter(User.email == "a@example.test").first().id).tenant_id
        db.add(User(tenant_id=tenant,email="audit-sec4@example.test",
                    password_hash=password_hash("test_password_12345"),role="auditor"))
        db.commit()
    auditor = auth("a", "audit-sec4@example.test")
    assert client.get("/api/v1/modules", headers=auditor).status_code == 403
    assert client.get("/api/v1/modules/summary", headers=auditor).status_code == 403
