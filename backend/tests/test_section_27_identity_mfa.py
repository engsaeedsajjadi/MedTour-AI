"""Section 27: two-step staff MFA, account lifecycle and role binding.

Only synthetic accounts. Never use a real patient's credentials.
"""
import base64,hashlib,os,time
import pytest
from app import identity_access as mfa
from app.models import User
from app.enterprise_models import StaffTotp,StaffMfaChallenge,RefreshSession,PhysicianAccount
from app.security import password_hash
from sqlalchemy import select

LOGIN="/api/v1/auth/login"
MFA="/api/v1/auth/mfa"

@pytest.fixture(autouse=True)
def mfa_key(monkeypatch):
    monkeypatch.setenv("MFA_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode())

def otp(secret):
    return mfa.code_for(secret,int(time.time())//30)

def activate(client,auth):
    admin=auth("a")
    start=client.post(MFA+"/enroll",headers=admin)
    assert start.status_code==200,start.text
    secret=start.json()["secret"]
    verified=client.post(MFA+"/confirm",headers=admin,json={"code":otp(secret)})
    assert verified.status_code==200,verified.text
    result=verified.json()
    assert result["enabled"] and result["access_token"] and result["refresh_token"]
    return secret,result,admin

def test_totp_enroll_encrypted_and_old_access_invalidated(context):
    client,auth,_,Session=context
    secret,issued,original=activate(client,auth)
    assert client.get("/api/v1/auth/me",headers=original).status_code==401
    updated={"Authorization":"Bearer "+issued["access_token"]}
    assert client.get(MFA+"/status",headers=updated).json()["enabled"] is True
    with Session() as db:
        row=db.query(StaffTotp).one()
        assert secret not in row.encrypted_secret
        assert row.enabled is True
        assert row.last_step>=0
        user=db.query(User).filter(User.email=="a@example.test").one()
        assert user.auth_version==1
        assert len(db.query(RefreshSession).all())>=2
    second=client.post(MFA+"/enroll",headers=updated)
    assert second.status_code==409

def test_mfa_password_only_never_returns_access_token(context):
    client,auth,_,Session=context
    secret,issued,_=activate(client,auth)
    password=client.post(LOGIN,json={
        "tenant_slug":"a","email":"a@example.test","password":"test_password_12345"})
    assert password.status_code==202,password.text
    challenge=password.json()
    assert challenge["mfa_required"]
    assert not challenge["access_token_issued"]
    assert "access_token" not in challenge and "refresh_token" not in challenge
    bad=client.post(MFA+"/verify",json={
        "challenge_token":challenge["challenge_token"],"code":"000000" if otp(secret)!="000000" else "999999"})
    assert bad.status_code==401
    # Enrollment's TOTP window is intentionally marked as used; advance
    # application time through monkeypatch (never sleep in tests).
    future=int(time.time())//30*30+70
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(mfa.time,"time",lambda:future)
        proper=mfa.code_for(secret,future//30)
        verified=client.post(MFA+"/verify",json={
            "challenge_token":challenge["challenge_token"],"code":proper})
    assert verified.status_code==200,verified.text
    assert verified.json()["access_token"]
    assert client.get("/api/v1/auth/me",headers={
        "Authorization":"Bearer "+verified.json()["access_token"]}).status_code==200
    assert client.post(MFA+"/verify",json={
        "challenge_token":challenge["challenge_token"],"code":proper}).status_code==401

def test_wrong_code_limited_five_attempts(context):
    client,auth,_,Session=context
    secret,_,_=activate(client,auth)
    result=client.post(LOGIN,json={
        "tenant_slug":"a","email":"a@example.test","password":"test_password_12345"})
    ticket=result.json()["challenge_token"]
    wrong="000000" if otp(secret)!="000000" else "999999"
    for _ in range(5):
        failure=client.post(MFA+"/verify",json={"challenge_token":ticket,"code":wrong})
        assert failure.status_code==401
    with Session() as db:
        row=db.query(StaffMfaChallenge).filter_by(challenge_hash=hashlib.sha256(ticket.encode()).hexdigest()).one()
        assert row.attempts==5 and row.used_at is not None
    future=int(time.time())//30*30+70
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(mfa.time,"time",lambda:future)
        good=mfa.code_for(secret,future//30)
        assert client.post(MFA+"/verify",json={
            "challenge_token":ticket,"code":good}).status_code==401

def test_mfa_tenant_isolation_and_missing_key_fails_closed(context,monkeypatch):
    client,auth,_,Session=context
    secret,_,_=activate(client,auth)
    second=auth("b")
    assert client.get(MFA+"/status",headers=second).json()["enabled"] is False
    monkeypatch.delenv("MFA_ENCRYPTION_KEY")
    blocked=client.post(LOGIN,json={
        "tenant_slug":"a","email":"a@example.test","password":"test_password_12345"})
    assert blocked.status_code==503
    assert client.get(MFA+"/status",headers=second).status_code==200
    assert client.post(MFA+"/enroll",headers=second).status_code==503

def test_password_rotation_and_staff_deactivation_revoke_tokens(context):
    client,auth,_,Session=context
    a=auth("a")
    op=auth("a","operator@example.test")
    assert client.get("/api/v1/auth/staff",headers=op).status_code==403
    with Session() as db:
        user=db.query(User).filter(User.email=="operator@example.test").one()
        uid=user.id
    result=client.put("/api/v1/auth/staff/"+uid+"/active",headers=a,json={"active":False})
    assert result.status_code==200,result.text
    assert client.get("/api/v1/auth/me",headers=op).status_code==401
    assert client.post(LOGIN,json={
        "tenant_slug":"a","email":"operator@example.test",
        "password":"test_password_12345"}).status_code==401
    assert client.put("/api/v1/auth/staff/"+uid+"/active",headers=a,json={"active":True}).status_code==200
    assert client.get("/api/v1/auth/me",headers=op).status_code==401
    rotated=client.post("/api/v1/auth/password/change",headers=a,json={
        "current_password":"test_password_12345",
        "new_password":"different-synthetic-strong-secret-27"})
    assert rotated.status_code==200,rotated.text
    assert client.get("/api/v1/auth/me",headers=a).status_code==401
    assert client.post(LOGIN,json={
        "tenant_slug":"a","email":"a@example.test","password":"test_password_12345"}).status_code==401
    assert client.post(LOGIN,json={
        "tenant_slug":"a","email":"a@example.test",
        "password":"different-synthetic-strong-secret-27"}).status_code==200

def test_physician_identity_requires_active_tenant_account(context):
    client,auth,tenants,Session=context
    with Session() as db:
        doctor=User(tenant_id=tenants[0],email="doctor27@example.test",
            role="physician",active=True,
            password_hash=password_hash("synthetic-doctor-password-27"))
        db.add(doctor);db.commit()
        uid=doctor.id
    blocked=client.post(LOGIN,json={"tenant_slug":"a",
        "email":"doctor27@example.test","password":"synthetic-doctor-password-27"})
    assert blocked.status_code==200
    unbound={"Authorization":"Bearer "+blocked.json()["access_token"]}
    assert client.get("/api/v1/auth/me",headers=unbound).status_code==200
    assert client.get("/api/v1/physician-management/portal/me",headers=unbound).status_code==403
    admin=auth("a")
    staff=client.get("/api/v1/auth/staff",headers=admin)
    assert staff.status_code==200
    assert any(x["id"]==uid for x in staff.json()["items"])
    other=auth("b")
    assert client.put("/api/v1/auth/staff/"+uid+"/active",headers=other,
        json={"active":False}).status_code==404
