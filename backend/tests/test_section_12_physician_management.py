"""Section 12 physician-specific accounts and directory evidence (synthetic only)."""
from datetime import datetime, timedelta, timezone

from app.models import User, Physician, Hospital, Audit
from app.enterprise_models import (
    PhysicianAccount, PhysicianCredential, PhysicianAffiliation,
    PhysicianAvailability,
)

ROOT = "/api/v1/physician-management"


def _account(client, admin, email="synthetic.physician@example.test"):
    created = client.post("/api/v1/staff", headers=admin, json={
        "email": email, "password": "synthetic_physician_pwd_123",
        "role": "physician",
    })
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _doctor(client, admin, name="Synthetic Physician"):
    r = client.post("/api/v1/physicians", headers=admin, json={
        "full_name": name, "specialty": "cardiology", "city": "Mashhad",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _attest(client, admin, pid, expires=None):
    return client.put(ROOT + f"/physicians/{pid}/credential", headers=admin, json={
        "issuing_country": "IR",
        "issuing_authority": "Synthetic credential source",
        "license_reference": "LICENSE-SYNTHETIC-12",
        "expires_at": (expires or (datetime.now(timezone.utc)+timedelta(days=90))).isoformat(),
    })


def _link(client, admin, pid, uid):
    return client.put(ROOT + f"/physicians/{pid}/account", headers=admin,
                      json={"user_id": uid})


def _login(client, email="synthetic.physician@example.test"):
    r = client.post("/api/v1/auth/login", json={
        "tenant_slug": "a", "email": email,
        "password": "synthetic_physician_pwd_123",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_physician_portal_requires_role_link_and_current_evidence(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    pid = _doctor(client, admin)
    uid = _account(client, admin)
    token = _login(client)
    assert client.get(ROOT+"/portal/me", headers=admin).status_code == 403
    assert client.get(ROOT+"/portal/me", headers=token).status_code == 403
    assert _link(client, admin, pid, uid).status_code == 200
    assert client.get(ROOT+"/portal/me", headers=token).status_code == 403
    evidence = _attest(client, admin, pid)
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["externally_verified"] is False
    portal = client.get(ROOT+"/portal/me", headers=token)
    assert portal.status_code == 200, portal.text
    assert portal.json()["physician_id"] == pid
    assert portal.json()["linked_user_id"] == uid
    assert portal.json()["regulator_licensure_verified"] is False
    assert "license_reference" not in portal.text
    assert client.get(ROOT+"/directory", headers=token).status_code == 403
    revoke = client.post(ROOT+f"/physicians/{pid}/credential/revoke",headers=admin)
    assert revoke.status_code == 200
    assert client.get(ROOT+"/portal/me",headers=token).status_code == 403
    assert client.post(ROOT+f"/physicians/{pid}/account/revoke",headers=admin).status_code == 200
    with Session() as db:
        row=db.query(PhysicianAccount).first()
        assert row.active is False
        assert db.query(Audit).filter(Audit.event=="physician_evidence_revoked").count() == 1


def test_account_mapping_rejects_cross_tenant_and_second_binding(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    pid=_doctor(client,admin)
    second=_doctor(client,admin,"Another physician")
    uid=_account(client,admin)
    foreign=client.get("/api/v1/auth/me",headers=auth("b")).json()["id"]
    assert _link(client,admin,pid,foreign).status_code==404
    assert _link(client,auth("b"),pid,uid).status_code==404
    assert _link(client,admin,pid,uid).status_code==200
    assert _link(client,admin,pid,uid).json()["reused"] is True
    assert _link(client,admin,second,uid).status_code==409
    another=_account(client,admin,"another.physician@example.test")
    assert _link(client,admin,pid,another).status_code==409
    assert _link(client,auth("a","operator@example.test"),second,another).status_code==403
    assert client.get(ROOT+"/directory",headers=auth("b")).json()["items"]==[]


def test_credential_expiry_validation_and_revocation_are_fail_closed(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    pid=_doctor(client,admin)
    uid=_account(client,admin)
    assert _link(client,admin,pid,uid).status_code==200
    tok=_login(client)
    assert _attest(client,admin,pid,datetime.now(timezone.utc)-timedelta(days=1)).status_code==422
    assert _attest(client,admin,pid,datetime.now(timezone.utc)+timedelta(days=1200)).status_code==422
    assert client.put(ROOT+f"/physicians/{pid}/credential",headers=admin,json={
        "issuing_country":"IR","issuing_authority":"Synthetic source",
        "license_reference":"VALID-REF-12",
        "expires_at":(datetime.now(timezone.utc)+timedelta(days=120)).replace(tzinfo=None).isoformat(),
    }).status_code==422
    assert _attest(client,admin,pid).status_code==200
    with Session() as db:
        cred=db.query(PhysicianCredential).first()
        cred.expires_at=datetime.now(timezone.utc)-timedelta(hours=1)
        db.commit()
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    assert _attest(client,admin,pid).status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==200


def test_physician_portal_only_sees_linked_referrals_and_appointments(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    pid=_doctor(client,admin)
    other=_doctor(client,admin,"Other cardiologist")
    uid=_account(client,admin)
    tok=_login(client)
    assert _link(client,admin,pid,uid).status_code==200
    assert _attest(client,admin,pid).status_code==200
    for identifier in (pid,other):
        verify=client.patch(f"/api/v1/physicians/{identifier}/verification",headers=admin,json={"status":"verified"})
        assert verify.status_code==200
    r1=client.post("/api/v1/referrals",headers=admin,json={"case_id":case["id"],"physician_id":pid})
    r2=client.post("/api/v1/referrals",headers=admin,json={"case_id":case["id"],"physician_id":other})
    assert r1.status_code==201 and r2.status_code==201
    future=(datetime.now(timezone.utc)+timedelta(days=5)).isoformat()
    appt=client.post("/api/v1/appointments",headers=admin,json={
        "case_id":case["id"],"physician_id":pid,"requested_at":future,
    })
    assert appt.status_code==201
    referrals=client.get(ROOT+"/portal/referrals",headers=tok)
    assert referrals.status_code==200
    assert len(referrals.json()["items"])==1
    assert referrals.json()["items"][0]["id"]==r1.json()["id"]
    assert "reviewer_note" not in referrals.text and "complaint" not in referrals.text
    appointments=client.get(ROOT+"/portal/appointments",headers=tok)
    assert appointments.status_code==200
    assert len(appointments.json()["items"])==1
    assert not appointments.json()["external_booking_verified"]
    assert client.get("/api/v1/cases/"+case["id"],headers=tok).status_code==403


def test_affiliation_is_tenant_bound_non_verified_and_revocable(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    pid=_doctor(client,admin)
    h=client.post("/api/v1/hospitals",headers=admin,json={"name":"Synthetic Clinic","city":"Mashhad"})
    assert h.status_code==201
    hid=h.json()["id"]
    url=ROOT+f"/physicians/{pid}/affiliations"
    assert client.post(url,headers=auth("a","operator@example.test"),json={"hospital_id":hid}).status_code==403
    assert client.post(url,headers=auth("b"),json={"hospital_id":hid}).status_code==404
    first=client.post(url,headers=admin,json={"hospital_id":hid})
    assert first.status_code==200, first.text
    assert first.json()["external_affiliation_verified"] is False
    assert client.post(url,headers=admin,json={"hospital_id":hid}).json()["reused"] is True
    entries=client.get(ROOT+"/directory",headers=admin).json()["items"]
    assert entries[0]["hospital_ids"]==[hid]
    rev=client.post(url+"/"+hid+"/revoke",headers=admin)
    assert rev.status_code==200
    assert client.get(ROOT+"/directory",headers=admin).json()["items"][0]["hospital_ids"]==[]
    with Session() as db:
        assert db.query(PhysicianAffiliation).count()==1


def test_availability_only_proposes_slots_and_detects_overlap(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    pid=_doctor(client,admin)
    uid=_account(client,admin)
    tok=_login(client)
    _link(client,admin,pid,uid)
    _attest(client,admin,pid)
    start=datetime.now(timezone.utc)+timedelta(days=3)
    end=start+timedelta(minutes=45)
    url=ROOT+f"/physicians/{pid}/availability"
    data={"starts_at":start.isoformat(),"ends_at":end.isoformat()}
    first=client.post(url,headers=admin,json=data)
    assert first.status_code==201,first.text
    assert first.json()["status"]=="proposed"
    assert not first.json()["appointment_booked"]
    assert client.post(url,headers=admin,json=data).status_code==409
    assert client.post(url,headers=admin,json={
        **data,"ends_at":(end+timedelta(hours=9)).isoformat()
    }).status_code==422
    assert client.post(url,headers=admin,json={
        "starts_at":start.replace(tzinfo=None).isoformat(),
        "ends_at":end.isoformat()
    }).status_code==422
    mine=client.get(ROOT+"/portal/availability",headers=tok)
    assert mine.status_code==200 and len(mine.json()["items"])==1
    assert not mine.json()["real_time_calendar_sync"]
    stopped=client.post(ROOT+"/availability/"+first.json()["id"]+"/cancel",headers=admin)
    assert stopped.status_code==200
    assert client.get(ROOT+"/portal/availability",headers=tok).json()["items"]==[]
    with Session() as db:
        assert db.query(PhysicianAvailability).count()==1


def test_legacy_directory_verified_flag_does_not_grant_portal_or_claim_licensure(seeded):
    (client,auth,tids,Session),admin,patient,case=seeded
    pid=_doctor(client,admin)
    uid=_account(client,admin)
    tok=_login(client)
    assert client.patch(f"/api/v1/physicians/{pid}/verification",headers=admin,
                        json={"status":"verified"}).status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    assert _link(client,admin,pid,uid).status_code==200
    assert client.get(ROOT+"/portal/me",headers=tok).status_code==403
    result=client.post("/api/v1/provider-options",headers=admin,json={"case_id":case["id"]})
    assert result.status_code==200
    assert result.json()["independent_licensure_verified"] is False
    assert "independent license NOT verified" in result.json()["results"][0]["matching_reason"]
    assert client.get(ROOT+"/directory",headers=admin).json()["externally_verified"] is False
