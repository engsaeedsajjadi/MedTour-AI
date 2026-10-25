"""Section 14: synthetic provider matching safety regressions."""
from datetime import datetime,timedelta,timezone
from app.enterprise_models import ProviderMatch
ROOT="/api/v1/provider-matching"

def doctor(client,admin,name="Synthetic Specialist",specialty="cardiology"):
    r=client.post("/api/v1/physicians",headers=admin,json={"full_name":name,"specialty":specialty,"city":"Mashhad"})
    assert r.status_code==201,r.text
    pid=r.json()["id"]
    c=client.put(f"/api/v1/physician-management/physicians/{pid}/credential",headers=admin,json={
        "issuing_country":"IR","issuing_authority":"Synthetic evidence",
        "license_reference":"SYNTH-PROV-14",
        "expires_at":(datetime.now(timezone.utc)+timedelta(days=90)).isoformat()})
    assert c.status_code==200,c.text
    return pid

def test_options_require_intake_consent_and_local_evidence(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid=doctor(client,admin)
    url=ROOT+f"/cases/{c['id']}/options"
    assert client.get(url).status_code==401
    assert client.get(url,headers=auth("b")).status_code==404
    data=client.get(url,headers=admin)
    assert data.status_code==200,data.text
    assert data.json()["items"][0]["physician_id"]==pid
    assert data.json()["independent_regulator_verification"] is False
    assert data.json()["clinical_ranking"] is False
    second=client.post("/api/v1/physicians",headers=admin,json={
        "full_name":"Unverified physician","specialty":"cardiology"}).json()
    assert all(x["physician_id"]!=second["id"] for x in data.json()["items"])
    revoke=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":False,"notice_version":"prov-14"})
    assert revoke.status_code==201
    assert client.get(url,headers=admin).status_code==409

def test_proposal_requires_human_review_and_is_tenant_scoped(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid=doctor(client,admin)
    url=ROOT+f"/cases/{c['id']}/proposals"
    first=client.post(url,headers=admin,json={"physician_id":pid})
    assert first.status_code==201,first.text
    mid=first.json()["id"]
    assert first.json()["status"]=="pending_human_review"
    assert first.json()["clinical_suitability_determined"] is False
    assert client.post(url,headers=admin,json={"physician_id":pid}).json()["reused"]
    assert len(client.get(url,headers=admin).json()["items"])==1
    assert client.get(url,headers=auth("b")).status_code==404
    review=ROOT+f"/proposals/{mid}/review"
    assert client.post(review,headers=auth("a","operator@example.test"),json={
        "decision":"administratively_shortlisted","reference":"ADMIN-REVIEW-14"}).status_code==403
    approved=client.post(review,headers=admin,json={
        "decision":"administratively_shortlisted","reference":"ADMIN-REVIEW-14"})
    assert approved.status_code==200,approved.text
    assert approved.json()["booking_created"] is False
    assert approved.json()["clinical_suitability_determined"] is False
    assert client.post(review,headers=admin,json={
        "decision":"rejected","reference":"OTHER-REVIEW-14"}).status_code==409
    with Session() as db:
        assert db.query(ProviderMatch).count()==1

def test_specialty_mismatch_and_expired_local_evidence_rejected(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid=doctor(client,admin,specialty="oncology")
    url=ROOT+f"/cases/{c['id']}/proposals"
    assert client.post(url,headers=admin,json={"physician_id":pid}).status_code==409
    match=doctor(client,admin,name="Correct specialty")
    revoked=client.post(f"/api/v1/physician-management/physicians/{match}/credential/revoke",headers=admin)
    assert revoked.status_code==200
    assert client.post(url,headers=admin,json={"physician_id":match}).status_code==409
    assert client.get(ROOT+f"/cases/{c['id']}/options",headers=admin).json()["items"]==[]

def test_unlinked_hospital_not_eligible(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid=doctor(client,admin)
    h=client.post("/api/v1/hospitals",headers=admin,json={"name":"Synthetic hospital"}).json()
    url=ROOT+f"/cases/{c['id']}/proposals"
    assert client.post(url,headers=admin,json={"physician_id":pid,"hospital_id":h["id"]}).status_code==409
    assert client.post(url,headers=auth("b"),json={"physician_id":pid}).status_code==404
