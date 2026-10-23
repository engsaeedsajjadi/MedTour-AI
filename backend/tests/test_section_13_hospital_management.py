"""Section 13 synthetic-only hospital management RBAC / consent / safety tests."""
from datetime import datetime, timedelta, timezone

from app.models import Audit
from app.enterprise_models import (
    HospitalAccount, HospitalCredential, HospitalService,
    HospitalCapacity, HospitalCoordination,
)

ROOT="/api/v1/hospital-management"


def create_hospital(client, admin, name="Synthetic Hospital"):
    r=client.post("/api/v1/hospitals",headers=admin,
                  json={"name":name,"city":"Mashhad"})
    assert r.status_code==201,r.text
    return r.json()["id"]


def create_account(client, admin, email="hospital.user@example.test"):
    r=client.post("/api/v1/staff",headers=admin,json={
        "email":email,"password":"SyntheticHospitalPassword123",
        "role":"hospital",
    })
    assert r.status_code==201,r.text
    return r.json()["id"]


def login(client,email="hospital.user@example.test"):
    r=client.post("/api/v1/auth/login",json={
        "tenant_slug":"a","email":email,"password":"SyntheticHospitalPassword123"
    })
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["access_token"]}


def evidence(client,admin,hid,expires=None):
    expires=expires or datetime.now(timezone.utc)+timedelta(days=120)
    return client.put(ROOT+f"/hospitals/{hid}/credential",headers=admin,json={
        "issuing_country":"IR","issuing_authority":"Synthetic license desk",
        "registration_reference":"SYNT-REG-000013",
        "expires_at":expires.isoformat(),
    })


def service(client,admin,hid,code="cardiology"):
    return client.post(ROOT+f"/hospitals/{hid}/services",headers=admin,
                       json={"service_code":code})



def allow_hospital_coordination(client,admin,patient_id,accepted=True):
    result=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":patient_id,"purpose":"hospital_coordination",
        "accepted":accepted,"notice_version":"synthetic-hospital-13",
    })
    assert result.status_code==201,result.text


def linked_setup(client,admin):
    hid=create_hospital(client,admin)
    uid=create_account(client,admin)
    tok=login(client)
    r=client.put(ROOT+f"/hospitals/{hid}/accounts",headers=admin,
                 json={"user_id":uid})
    assert r.status_code==200,r.text
    r=evidence(client,admin,hid)
    assert r.status_code==200,r.text
    return hid,uid,tok


def test_hospital_portal_requires_role_local_evidence_and_revoke(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid=create_hospital(client,admin)
    uid=create_account(client,admin)
    tok=login(client)
    assert client.get(ROOT+"/portal/me",headers=admin).status_code==403
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    l=client.put(ROOT+f"/hospitals/{hid}/accounts",headers=admin,
                 json={"user_id":uid})
    assert l.status_code==200,l.text
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    approved=evidence(client,admin,hid)
    assert approved.status_code==200,approved.text
    assert approved.json()["regulator_license_verified"] is False
    profile=client.get(ROOT+"/portal/me",headers=tok)
    assert profile.status_code==200,profile.text
    assert profile.json()["hospital_id"]==hid
    assert profile.json()["regulator_license_verified"] is False
    assert "registration_reference" not in profile.text
    assert "linked_user_ids" not in profile.text
    assert client.get(ROOT+"/directory",headers=tok).status_code==403
    assert client.put(ROOT+f"/hospitals/{hid}/credential",
                      headers=tok,json={}).status_code==403
    assert client.post(ROOT+f"/hospitals/{hid}/credential/revoke",
                       headers=admin).status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    assert evidence(client,admin,hid).status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==200
    revoke=client.post(ROOT+f"/hospitals/{hid}/accounts/{uid}/revoke",headers=admin)
    assert revoke.status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    with Session() as db:
        assert db.query(HospitalAccount).first().active is False
        assert db.query(HospitalCredential).count()==1


def test_tenant_boundary_staff_account_and_exclusive_identity(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid=create_hospital(client,admin)
    second=create_hospital(client,admin,"Second synthetic hospital")
    uid=create_account(client,admin)
    foreign=client.get("/api/v1/auth/me",headers=auth("b")).json()["id"]
    path=ROOT+f"/hospitals/{hid}/accounts"
    assert client.put(path,headers=admin,json={"user_id":foreign}).status_code==404
    assert client.put(path,headers=auth("b"),json={"user_id":uid}).status_code==404
    assert client.put(path,headers=admin,json={"user_id":uid}).status_code==200
    assert client.put(path,headers=admin,json={"user_id":uid}).json()["reused"]
    assert client.put(ROOT+f"/hospitals/{second}/accounts",
                      headers=admin,json={"user_id":uid}).status_code==409
    assert client.get(ROOT+"/directory",headers=auth("b")).json()["items"]==[]
    assert client.put(path,headers=auth("a","operator@example.test"),
                      json={"user_id":uid}).status_code==403


def test_credential_expiry_validation_and_real_independent_status(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid,uid,tok=linked_setup(client,admin)
    assert evidence(client,admin,hid,datetime.now(timezone.utc)-timedelta(days=1)).status_code==422
    assert evidence(client,admin,hid,datetime.now(timezone.utc)+timedelta(days=1100)).status_code==422
    assert client.put(ROOT+f"/hospitals/{hid}/credential",headers=admin,json={
        "issuing_country":"IR","issuing_authority":"Synthetic provider",
        "registration_reference":"LICENSE-000013",
        "expires_at":(datetime.now(timezone.utc)+timedelta(days=90)).replace(tzinfo=None).isoformat(),
    }).status_code==422
    with Session() as db:
        db.query(HospitalCredential).first().expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    directory=client.get(ROOT+"/directory",headers=admin).json()["items"]
    assert directory[0]["evidence_status"]=="expired"
    assert directory[0]["regulator_license_verified"] is False


def test_service_catalog_and_proposed_capacity_only(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid,uid,tok=linked_setup(client,admin)
    assert service(client,admin,hid).status_code==200
    assert service(client,admin,hid).json()["reused"] is True
    future=datetime.now(timezone.utc)+timedelta(days=5)
    body={"service_code":"cardiology","starts_at":future.isoformat(),
          "ends_at":(future+timedelta(hours=2)).isoformat(),"proposed_units":3}
    url=ROOT+f"/hospitals/{hid}/capacity"
    first=client.post(url,headers=admin,json=body)
    assert first.status_code==201,first.text
    assert first.json()["status"]=="proposed"
    assert first.json()["live_capacity_verified"] is False
    assert not first.json()["external_booking_created"]
    assert client.post(url,headers=admin,json=body).status_code==409
    assert client.post(url,headers=admin,json={**body,"proposed_units":0}).status_code==422
    assert client.post(url,headers=admin,json={**body,"ends_at":
                       (future+timedelta(days=2)).isoformat()}).status_code==422
    assert client.post(url,headers=admin,json={**body,"service_code":"oncology"}).status_code==409
    slots=client.get(ROOT+"/portal/capacity",headers=tok)
    assert slots.status_code==200 and len(slots.json()["items"])==1
    assert slots.json()["reservable"] is False
    assert client.post(ROOT+f"/capacity/{first.json()['id']}/cancel",headers=admin).status_code==200
    assert client.get(ROOT+"/portal/capacity",headers=tok).json()["items"]==[]
    assert service(client,admin,hid,"oncology").status_code==200
    assert client.post(ROOT+f"/hospitals/{hid}/services/oncology/revoke",headers=admin).status_code==200
    assert client.post(url,headers=admin,json={**body,"service_code":"oncology"}).status_code==409
    with Session() as db:
        assert db.query(HospitalService).count()==2
        assert db.query(HospitalCapacity).count()==1


def test_coordination_receipt_requires_tenant_consent_and_no_external_confirmation(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid,uid,tok=linked_setup(client,admin)
    assert service(client,admin,hid).status_code==200
    url=ROOT+f"/hospitals/{hid}/coordinations"
    data={"case_id":case["id"],"service_code":"cardiology",
          "reference":"TEST-HOSP-REQ-0013"}
    # Intake alone is NOT permission to expose coordination metadata to a hospital.
    assert client.post(url,headers=admin,json=data).status_code==409
    allow_hospital_coordination(client,admin,p["id"])
    assert client.post(url,headers=auth("a","operator@example.test"),json=data).status_code==403
    assert client.post(url,headers=auth("b"),json=data).status_code==404
    req=client.post(url,headers=admin,json=data)
    assert req.status_code==201,req.text
    assert req.json()["booking_confirmed"] is False
    cid=req.json()["id"]
    duplicate=client.post(url,headers=admin,json=data)
    assert duplicate.status_code==201 and duplicate.json()["reused"] is True
    conflicting=client.post(url,headers=admin,json={**data,"service_code":"oncology"})
    assert conflicting.status_code==409
    staff_queue=client.get(ROOT+"/portal/coordinations",headers=tok)
    assert staff_queue.status_code==200,staff_queue.text
    assert len(staff_queue.json()["items"])==1
    assert "complaint" not in staff_queue.text and "Synthetic Patient" not in staff_queue.text
    assert staff_queue.json()["items"][0]["case_reference"]==case["id"]
    assert client.post(ROOT+f"/portal/coordinations/{cid}/acknowledge",headers=admin).status_code==403
    received=client.post(ROOT+f"/portal/coordinations/{cid}/acknowledge",headers=tok)
    assert received.status_code==200,received.text
    assert received.json()["status"]=="received"
    assert received.json()["hospital_booking_confirmed"] is False
    assert client.post(ROOT+f"/portal/coordinations/{cid}/acknowledge",headers=tok).status_code==409
    with Session() as db:
        assert db.query(HospitalCoordination).count()==1
        assert db.query(Audit).filter(Audit.event=="hospital_coordination_received").count()==1


def test_consent_withdrawal_blocks_requests_permanently_and_other_hospitals(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid,uid,tok=linked_setup(client,admin)
    hid2=create_hospital(client,admin,"Separate Clinic")
    uid2=create_account(client,admin,"hospital.second@example.test")
    assert client.put(ROOT+f"/hospitals/{hid2}/accounts",headers=admin,
                      json={"user_id":uid2}).status_code==200
    assert evidence(client,admin,hid2).status_code==200
    tok2=login(client,"hospital.second@example.test")
    assert service(client,admin,hid).status_code==200
    data={"case_id":case["id"],"service_code":"cardiology",
          "reference":"CONSENT-REQ-0013"}
    allow_hospital_coordination(client,admin,p["id"])
    cid=client.post(ROOT+f"/hospitals/{hid}/coordinations",
                    headers=admin,json=data).json()["id"]
    assert client.get(ROOT+"/portal/coordinations",headers=tok2).json()["items"]==[]
    assert client.post(ROOT+f"/portal/coordinations/{cid}/acknowledge",
                       headers=tok2).status_code==404
    revoked=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":False,
        "notice_version":"synthetic-13-revocation",
    })
    assert revoked.status_code==201,revoked.text
    assert client.get(ROOT+"/portal/coordinations",headers=tok).json()["items"]==[]
    assert client.post(ROOT+f"/portal/coordinations/{cid}/acknowledge",
                       headers=tok).status_code==409
    with Session() as db:
        assert db.get(HospitalCoordination,cid).status=="blocked"
    assert client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":True,
        "notice_version":"synthetic-13-resumed",
    }).status_code==201
    assert client.get(ROOT+"/portal/coordinations",headers=tok).json()["items"]==[]
    assert client.post(ROOT+f"/hospitals/{hid}/coordinations/{cid}/cancel",
                       headers=admin).status_code==200


def test_user_deactivation_requires_unlink_first(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid,uid,tok=linked_setup(client,admin)
    assert client.post(f"/api/v1/admin-center/staff/{uid}/deactivate",
                       headers=admin).status_code==409
    assert client.post(ROOT+f"/hospitals/{hid}/accounts/{uid}/revoke",
                       headers=admin).status_code==200
    assert client.post(f"/api/v1/admin-center/staff/{uid}/deactivate",
                       headers=admin).status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==401


def test_specific_hospital_consent_withdrawal_blocks_metadata_even_if_intake_remains(seeded):
    (client,auth,tids,Session),admin,p,case=seeded
    hid,uid,tok=linked_setup(client,admin)
    assert service(client,admin,hid).status_code==200
    allow_hospital_coordination(client,admin,p["id"])
    request=client.post(ROOT+f"/hospitals/{hid}/coordinations",headers=admin,json={
        "case_id":case["id"],"service_code":"cardiology",
        "reference":"SCOPE-CONSENT-0013"
    })
    assert request.status_code==201,request.text
    identifier=request.json()["id"]
    allow_hospital_coordination(client,admin,p["id"],accepted=False)
    assert client.get(ROOT+"/portal/coordinations",headers=tok).json()["items"]==[]
    assert client.post(ROOT+f"/portal/coordinations/{identifier}/acknowledge",
                       headers=tok).status_code==409
    with Session() as db:
        assert db.get(HospitalCoordination,identifier).status=="blocked"
    allow_hospital_coordination(client,admin,p["id"])
    assert client.get(ROOT+"/portal/coordinations",headers=tok).json()["items"]==[]
