"""Section 40: synthetic multi-step patient journey, no live provider or PHI."""
from sqlalchemy import select
from app.models import Audit, Case, Patient

def test_intake_consent_case_then_withdrawal_blocks_new_case(context):
    client,auth,tenants,Session=context
    a=auth("a")
    b=auth("b")
    payload={"full_name":"Synthetic Test Person","language":"fa","country":"AF"}
    p=client.post("/api/v1/patients",headers=a,json=payload)
    assert p.status_code==201,p.text
    pid=p.json()["id"]
    case_input={"patient_id":pid,"complaint":"synthetic administrative inquiry","specialty":"cardiology"}
    # A real tenant cannot open the case until its patient has consented.
    blocked=client.post("/api/v1/cases",headers=a,json=case_input)
    assert blocked.status_code==409,blocked.text
    assert client.get(f"/api/v1/patients/{pid}",headers=b).status_code==404
    consent=client.post("/api/v1/consents",headers=a,json={
        "patient_id":pid,"purpose":"intake","accepted":True,"notice_version":"synthetic-v1"})
    assert consent.status_code==201,consent.text
    created=client.post("/api/v1/cases",headers=a,json=case_input)
    assert created.status_code==201,created.text
    cid=created.json()["id"]
    assert client.get(f"/api/v1/cases/{cid}",headers=b).status_code==404
    assert any(x["id"]==cid for x in client.get("/api/v1/cases",headers=a).json())
    withdraw=client.post("/api/v1/consents",headers=a,json={
        "patient_id":pid,"purpose":"intake","accepted":False,"notice_version":"synthetic-v2"})
    assert withdraw.status_code==201,withdraw.text
    denied=client.post("/api/v1/cases",headers=a,json=case_input)
    assert denied.status_code==409,denied.text
    with Session() as db:
        a_events=list(db.scalars(select(Audit).where(Audit.tenant_id==tenants[0])).all())
        b_events=list(db.scalars(select(Audit).where(Audit.tenant_id==tenants[1])).all())
        assert any(e.event=="consent_withdrawn" for e in a_events)
        assert not any(e.event=="consent_withdrawn" for e in b_events)
        assert db.get(Patient,pid).tenant_id==tenants[0]
        assert db.get(Case,cid).tenant_id==tenants[0]
