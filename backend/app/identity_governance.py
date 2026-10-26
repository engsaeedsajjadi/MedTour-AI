"""Staff MFA enrollment, recovery-free reset and doctor-scoped case access.

No account MFA disable/recovery without independent identity assurance.
Doctor view is a minimal nonclinical case summary, not medical credentials
proof, diagnosis or permission to modify patient/case records.
"""
from __future__ import annotations
import base64,secrets,urllib.parse
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Case,Audit
from .enterprise_models import StaffMFA,DoctorCaseGrant
from .security import current_user,roles
from .staff_mfa import encrypted,decrypted,totp,row_for,verify
from .rate_limit import throttle

router=APIRouter(prefix="/api/v1/identity",tags=["staff MFA and case-scoped physician access"])
ADMIN=roles("admin")
DOCTOR=roles("doctor")

class CodeIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    code:str=Field(min_length=6,max_length=6,pattern=r"^[0-9]{6}$")

@router.get("/mfa/status")
def status(user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=row_for(db,user.tenant_id,user.id)
    return {"enrolled":bool(row and row.enabled),"setup_pending":bool(row and not row.enabled),
        "independent_identity_verified":False,"self_service_mfa_disable":False}

@router.post("/mfa/setup")
def setup(user:User=Depends(current_user),db:Session=Depends(get_db)):
    existing=row_for(db,user.tenant_id,user.id,True)
    if existing and existing.enabled:raise HTTPException(409,"MFA already active")
    seed=secrets.token_bytes(20)
    raw=base64.b32encode(seed).decode().rstrip("=")
    if existing:existing.secret_encrypted=encrypted(seed,user.tenant_id,user.id);existing.last_counter=-1
    else:db.add(StaffMFA(tenant_id=user.tenant_id,user_id=user.id,
        enabled=False,last_counter=-1,secret_encrypted=encrypted(seed,user.tenant_id,user.id)))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="staff_mfa_setup_started",
        entity_type="User",entity_id=user.id))
    db.commit()
    issuer="MedTour-AI"
    url=f"otpauth://totp/{urllib.parse.quote(issuer+':'+user.email)}?"+urllib.parse.urlencode({
        "secret":raw,"issuer":issuer,"algorithm":"SHA1","digits":6,"period":30})
    return {"manual_secret":raw,"otp_auth_uri":url,
        "message":"Only shown once. Never copy into patient messages or logs.",
        "activated":False}

@router.post("/mfa/activate")
def activate(body:CodeIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    throttle("mfa-activate:"+user.tenant_id+":"+user.id,limit=8,window=600)
    row=row_for(db,user.tenant_id,user.id,True)
    if not row or row.enabled:raise HTTPException(409,"No pending MFA setup")
    now=__import__("time").time()
    counter=int(now//30)
    seed=decrypted(row)
    matches=[t for t in (counter-1,counter,counter+1) if t>row.last_counter and
        __import__("hmac").compare_digest(totp(seed,t),body.code)]
    if not matches:raise HTTPException(401,"Invalid MFA code")
    row.enabled=True;row.last_counter=max(matches)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="staff_mfa_activated",
        entity_type="User",entity_id=user.id))
    db.commit()
    return {"enrolled":True,"disable_available":False}

class AssignDoctorIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    user_id:str

@router.post("/doctor-grants/{case_id}",status_code=201)
def grant(case_id:str,body:AssignDoctorIn,db:Session=Depends(get_db),
          admin:User=Depends(ADMIN)):
    case=db.scalar(select(Case).where(Case.tenant_id==admin.tenant_id,Case.id==case_id))
    doctor=db.scalar(select(User).where(User.tenant_id==admin.tenant_id,
        User.id==body.user_id,User.active.is_(True),User.role=="doctor"))
    if not case or not doctor:raise HTTPException(404,"Case or doctor not found")
    record=db.scalar(select(DoctorCaseGrant).where(
        DoctorCaseGrant.tenant_id==admin.tenant_id,DoctorCaseGrant.case_id==case_id,
        DoctorCaseGrant.user_id==doctor.id).with_for_update())
    if record and record.revoked_at is None:raise HTTPException(409,"Already assigned")
    if record:record.revoked_at=None;record.granted_by=admin.id
    else:db.add(DoctorCaseGrant(tenant_id=admin.tenant_id,case_id=case_id,
        user_id=doctor.id,granted_by=admin.id))
    db.add(Audit(tenant_id=admin.tenant_id,user_id=admin.id,event="doctor_case_access_granted",
        entity_type="Case",entity_id=case_id))
    db.commit()
    return {"assigned":True,"case_id":case_id,"doctor_user_id":doctor.id}

@router.delete("/doctor-grants/{case_id}/{user_id}")
def revoke(case_id:str,user_id:str,db:Session=Depends(get_db),admin:User=Depends(ADMIN)):
    row=db.scalar(select(DoctorCaseGrant).where(
        DoctorCaseGrant.tenant_id==admin.tenant_id,DoctorCaseGrant.case_id==case_id,
        DoctorCaseGrant.user_id==user_id,DoctorCaseGrant.revoked_at.is_(None)).with_for_update())
    if not row:raise HTTPException(404,"Active grant not found")
    from .models import utcnow
    row.revoked_at=utcnow()
    db.add(Audit(tenant_id=admin.tenant_id,user_id=admin.id,
        event="doctor_case_access_revoked",entity_type="Case",entity_id=case_id))
    db.commit();return {"revoked":True}

@router.get("/doctor/cases")
def doctor_cases(db:Session=Depends(get_db),user:User=Depends(DOCTOR)):
    assigned=db.execute(select(Case.id,Case.specialty,Case.status).join(
        DoctorCaseGrant,DoctorCaseGrant.case_id==Case.id).where(
        Case.tenant_id==user.tenant_id,DoctorCaseGrant.tenant_id==user.tenant_id,
        DoctorCaseGrant.user_id==user.id,DoctorCaseGrant.revoked_at.is_(None))).all()
    return {"items":[{"id":x.id,"specialty":x.specialty,"status":x.status}
        for x in assigned],"clinical_decision_authorized":False,
        "patient_documents_accessible":False}

@router.get("/doctor/cases/{case_id}")
def doctor_case(case_id:str,db:Session=Depends(get_db),user:User=Depends(DOCTOR)):
    result=db.execute(select(Case.id,Case.specialty,Case.status).join(
        DoctorCaseGrant,DoctorCaseGrant.case_id==Case.id).where(
        Case.id==case_id,Case.tenant_id==user.tenant_id,
        DoctorCaseGrant.tenant_id==user.tenant_id,
        DoctorCaseGrant.user_id==user.id,DoctorCaseGrant.revoked_at.is_(None))).one_or_none()
    if result is None:raise HTTPException(404,"Case not assigned")
    return {"id":result.id,"specialty":result.specialty,"status":result.status,
        "documents":None,"clinical_decision_authorized":False}
