"""Section 21: synthetic OTP gateway and patient consent security.
Code shown to staff only in local/test; NO real identity verification.
"""
from datetime import datetime,timedelta,timezone
from app.enterprise_models import PortalAccess,PortalLoginChallenge
from app.models import Consent,Patient

BASE="/api/v1/portal"

def issue(client,staff,patient_id):
    r=client.post(BASE+"/invites/"+patient_id,headers=staff)
    assert r.status_code==201,r.text
    return r.json()

def exchange(client,invite,code=None):
    return client.post(BASE+"/session/exchange",json={
        "invitation_token":invite["token"],
        "verification_code":invite["demo_verification_code"] if code is None else code})

def authorized(client,invite):
    r=exchange(client,invite)
    assert r.status_code==201,r.text
    return {"X-Patient-Access":r.json()["access_token"]}

def communication(client,staff,patient_id):
    r=client.post("/api/v1/consents",headers=staff,json={
        "patient_id":patient_id,"purpose":"communication",
        "accepted":True,"notice_version":"v21-synthetic"})
    assert r.status_code==201,r.text

def test_invite_is_not_session_otp_required_and_single_use(seeded):
    (client,auth,_,Session),staff,patient,case=seeded
    assert client.post(BASE+"/invites/"+patient["id"],headers=staff).status_code==409
    communication(client,staff,patient["id"])
    i=issue(client,staff,patient["id"])
    assert i["access_enabled"] is False
    assert i["independent_identity_verified"] is False
    assert i["otp_delivery"]=="manual_staff_demo_only"
    assert client.get(BASE+"/me",headers={"X-Patient-Access":i["token"]}).status_code==401
    assert client.get(BASE+"/journey",headers={"X-Patient-Access":i["token"]}).status_code==401
    for path in ["/api/v1/secure-documents/portal/cases/"+case["id"]+"/list",
                 BASE+"/chat",BASE+"/consents"]:
        assert client.get(path,headers={"X-Patient-Access":i["token"]}).status_code==401
    with Session() as db:
        c=db.query(PortalLoginChallenge).one()
        assert i["demo_verification_code"] not in c.code_hash
        assert i["token"] not in c.invitation_hash
        assert db.query(PortalAccess).count()==0
    h=authorized(client,i)
    assert len(h["X-Patient-Access"])>=35
    assert h["X-Patient-Access"]!=i["token"]
    assert client.get(BASE+"/me",headers=h).json()["id"]==patient["id"]
    assert client.get(BASE+"/journey",headers=h).json()[0]["case_id"]==case["id"]
    assert exchange(client,i).status_code==401
    with Session() as db:
        assert db.query(PortalAccess).count()==1

def test_wrong_codes_max_attempts_and_expired_invites(seeded):
    (client,auth,_,Session),staff,patient,_=seeded
    communication(client,staff,patient["id"])
    i=issue(client,staff,patient["id"])
    wrong="000000" if i["demo_verification_code"]!="000000" else "999999"
    for _ in range(5):
        assert exchange(client,i,wrong).status_code==401
    assert exchange(client,i).status_code==401
    with Session() as db:
        row=db.query(PortalLoginChallenge).one()
        assert row.attempts==5 and row.consumed_at is not None
        assert db.query(PortalAccess).count()==0
    newer=issue(client,staff,patient["id"])
    with Session() as db:
        c=db.query(PortalLoginChallenge).filter(
            PortalLoginChallenge.invitation_hash!=row.invitation_hash).one()
        c.expires_at=datetime.now(timezone.utc)-timedelta(minutes=1)
        db.commit()
    assert exchange(client,newer).status_code==401
    assert exchange(client,newer).status_code==401
    assert client.post(BASE+"/session/exchange",json={
        "invitation_token":"short","verification_code":"888888"}).status_code==422
    with Session() as db:assert db.query(PortalAccess).count()==0

def test_invitation_rotation_revoke_logout_and_expiry(seeded):
    (client,auth,_,Session),staff,p,_=seeded
    communication(client,staff,p["id"])
    first=issue(client,staff,p["id"])
    second=issue(client,staff,p["id"])
    assert exchange(client,first).status_code==401
    h=authorized(client,second)
    assert client.get(BASE+"/me",headers=h).status_code==200
    new_invite=issue(client,staff,p["id"])
    assert client.get(BASE+"/me",headers=h).status_code==401
    session=authorized(client,new_invite)
    assert client.post(BASE+"/session/logout",headers=session).json()["logged_out"] is True
    assert client.get(BASE+"/me",headers=session).status_code==401
    active=issue(client,staff,p["id"])
    h2=authorized(client,active)
    with Session() as db:
        row=db.query(PortalAccess).filter(PortalAccess.revoked.is_(False)).one()
        row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    assert client.get(BASE+"/me",headers=h2).status_code==401
    pending=issue(client,staff,p["id"])
    rev=client.post(BASE+"/invites/revoke/"+p["id"],headers=staff)
    assert rev.status_code==200 and rev.json()["pending_invitations_revoked"]>=1
    assert exchange(client,pending).status_code==401

def test_patient_consent_self_service_and_immediate_access_revoke(seeded):
    (client,auth,_,Session),staff,p,_=seeded
    communication(client,staff,p["id"])
    access=authorized(client,issue(client,staff,p["id"]))
    view=client.get(BASE+"/consents",headers=access)
    assert view.status_code==200
    assert view.json()["purposes"]["intake"] is True
    assert view.json()["purposes"]["communication"] is True
    assert view.json()["purposes"]["medical_documents"] is False
    grant=client.post(BASE+"/consents",headers=access,json={
        "purpose":"medical_documents","accepted":True,"notice_version":"v21-synthetic"})
    assert grant.status_code==201 and grant.json()["source"]=="patient_portal_demo"
    assert client.get(BASE+"/consents",headers=access).json()["purposes"]["medical_documents"] is True
    bad=client.post(BASE+"/consents",headers=access,json={
        "purpose":"unexpected_purpose","accepted":False,"notice_version":"v21"})
    assert bad.status_code==422
    remove=client.post(BASE+"/consents",headers=access,json={
        "purpose":"medical_documents","accepted":False,"notice_version":"v21-synthetic"})
    assert remove.status_code==201
    assert client.get(BASE+"/me",headers=access).status_code==401
    with Session() as db:
        q=db.query(Consent).filter(Consent.patient_id==p["id"],
            Consent.purpose=="medical_documents").order_by(Consent.created_at.desc(),Consent.id.desc()).first()
        assert q.accepted is False
    new_access=authorized(client,issue(client,staff,p["id"]))
    assert client.get(BASE+"/consents",headers=new_access).json()["purposes"]["medical_documents"] is False
    assert client.post(BASE+"/consents",headers=new_access,json={
        "purpose":"communication","accepted":False,"notice_version":"v21-synthetic"}).status_code==201
    assert client.get(BASE+"/me",headers=new_access).status_code==401
    assert client.post(BASE+"/invites/"+p["id"],headers=staff).status_code==409

def test_staff_revocation_blocks_pending_challenge_after_consent_withdrawal(seeded):
    (client,auth,_,Session),staff,p,_=seeded
    communication(client,staff,p["id"])
    pending=issue(client,staff,p["id"])
    withdrawn=client.post("/api/v1/consents",headers=staff,json={
        "patient_id":p["id"],"purpose":"communication",
        "accepted":False,"notice_version":"v21-synthetic"})
    assert withdrawn.status_code==201,withdrawn.text
    assert exchange(client,pending).status_code==401
    with Session() as db:
        c=db.query(PortalLoginChallenge).one()
        assert c.consumed_at is not None

def test_cross_tenant_privacy_and_demo_mode_fail_closed(seeded,monkeypatch):
    (client,auth,_,Session),staff,p,_=seeded
    other=auth("b")
    assert client.post(BASE+"/invites/"+p["id"],headers=other).status_code==404
    communication(client,staff,p["id"])
    pending=issue(client,staff,p["id"])
    assert client.post(BASE+"/invites/revoke/"+p["id"],headers=other).status_code==404
    assert client.get(BASE+"/journey",headers={"X-Patient-Access":pending["token"]}).status_code==401
    monkeypatch.setenv("APP_ENV","staging")
    assert client.post(BASE+"/invites/"+p["id"],headers=staff).status_code==503
    assert exchange(client,pending).status_code==503
    monkeypatch.setenv("APP_ENV","test")
    good=authorized(client,pending)
    assert client.get(BASE+"/me",headers=good).status_code==200


def test_invitation_rate_limit_per_patient(seeded):
    (client,auth,_,Session),staff,p,_=seeded
    communication(client,staff,p["id"])
    for n in range(8):
        result=client.post(BASE+"/invites/"+p["id"],headers=staff)
        assert result.status_code==201,(n,result.text)
    blocked=client.post(BASE+"/invites/"+p["id"],headers=staff)
    assert blocked.status_code==429,blocked.text
    with Session() as db:
        rows=db.query(PortalLoginChallenge).filter(
            PortalLoginChallenge.patient_id==p["id"]).all()
        assert len(rows)==8
