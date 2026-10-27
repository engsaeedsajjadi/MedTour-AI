"""Section 27 MFA and isolated doctor-case grants with synthetic accounts."""
import base64,os,time,uuid
from app.models import User,Case,Patient
from app.security import password_hash
from app.staff_mfa import totp

BASE="/api/v1/identity"
def enroll(client,auth,Session):
    os.environ["STAFF_MFA_ENCRYPTION_KEY"]=base64.urlsafe_b64encode(b"x"*32).decode()
    begin=client.post(BASE+"/mfa/setup",headers=auth)
    assert begin.status_code==200,begin.text
    seed=base64.b32decode(begin.json()["manual_secret"]+"="*(-len(begin.json()["manual_secret"])%8))
    current=totp(seed,int(time.time()/30))
    activated=client.post(BASE+"/mfa/activate",headers=auth,json={"code":current})
    assert activated.status_code==200,activated.text
    return seed

def test_enrollment_verification_login_and_replay(context):
    client,auth,_,Session=context
    admin=auth("a")
    data={"tenant_slug":"a","email":"a@example.test","password":"test_password_12345"}
    before=client.post("/api/v1/auth/login",json=data)
    assert before.status_code==200
    seed=enroll(client,admin,Session)
    assert client.post("/api/v1/auth/refresh",json={
        "refresh_token":before.json()["refresh_token"]}).status_code==401
    assert client.post("/api/v1/auth/login",json=data).status_code==401
    wrong=client.post("/api/v1/auth/login",json=data|{"totp_code":"000000"})
    assert wrong.status_code==401
    # Activation counter cannot be reused; wait-free next-window check using
    # monkeypatch of module clock.
    import app.staff_mfa as mfa
    now=int(time.time())
    original=mfa.time.time
    mfa.time.time=lambda:now+30
    try:
        code=totp(seed,int((now+30)//30))
        good=client.post("/api/v1/auth/login",json=data|{"totp_code":code})
        assert good.status_code==200,good.text
        assert client.post("/api/v1/auth/login",json=data|{"totp_code":code}).status_code==401
    finally:mfa.time.time=original
    # A pre-MFA JWT no longer authenticates once MFA is activated.
    assert client.get(BASE+"/mfa/status",headers=admin).status_code==401
    new_auth={"Authorization":"Bearer "+good.json()["access_token"]}
    assert client.get(BASE+"/mfa/status",headers=new_auth).json()["enrolled"]
    assert client.post(BASE+"/mfa/setup",headers=new_auth).status_code==409

def test_doctor_case_grants_no_cross_tenant_access(context):
    client,auth,tids,Session=context
    a=auth("a");b=auth("b")
    with Session() as db:
        doctor=User(tenant_id=tids[0],email="synthetic-doctor@example.test",
            password_hash=password_hash("synthetic-test-password-12345"),role="doctor")
        foreign=User(tenant_id=tids[1],email="synthetic-doctor@example.test",
            password_hash=password_hash("synthetic-test-password-12345"),role="doctor")
        p=Patient(tenant_id=tids[0],full_name="Synthetic patient",language="en")
        db.add_all([doctor,foreign,p]);db.flush()
        c1=Case(tenant_id=tids[0],patient_id=p.id,specialty="administrative",status="new")
        c2=Case(tenant_id=tids[0],patient_id=p.id,specialty="another",status="new")
        db.add_all([c1,c2]);db.commit()
        uid=doctor.id;fid=foreign.id;cid=c1.id;other=c2.id
    doc=client.post("/api/v1/auth/login",json={"tenant_slug":"a",
        "email":"synthetic-doctor@example.test","password":"synthetic-test-password-12345"})
    assert doc.status_code==200,doc.text
    d={"Authorization":"Bearer "+doc.json()["access_token"]}
    assert client.get("/api/v1/patients",headers=d).status_code==403
    assert client.get(BASE+"/doctor/cases",headers=d).json()["items"]==[]
    assert client.post(BASE+"/doctor-grants/"+cid,headers=b,json={"user_id":uid}).status_code==404
    assert client.post(BASE+"/doctor-grants/"+cid,headers=a,json={"user_id":fid}).status_code==404
    grant=client.post(BASE+"/doctor-grants/"+cid,headers=a,json={"user_id":uid})
    assert grant.status_code==201,grant.text
    assert client.get(BASE+"/doctor/cases/"+cid,headers=d).status_code==200
    assert client.get(BASE+"/doctor/cases/"+other,headers=d).status_code==404
    assert len(client.get(BASE+"/doctor/cases",headers=d).json()["items"])==1
    assert client.post(BASE+"/doctor-grants/"+cid,headers=a,json={"user_id":uid}).status_code==409
    assert client.delete(BASE+"/doctor-grants/"+cid+"/"+uid,headers=a).status_code==200
    assert client.get(BASE+"/doctor/cases/"+cid,headers=d).status_code==404
