"""Section 21: dev-only patient portal two-step challenge and self-service consent.

Code returned to authorized staff for manual demo handoff, never SMS/email verified.
Not independently assured identity, MFA, or approval for real patient/PHI.
"""
from __future__ import annotations
import hashlib,hmac,secrets,os
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Header
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Patient,Consent,Audit,User
from .enterprise_models import PortalAccess,PortalLoginChallenge
from .security import roles,secret
from .safety_rules import active_consent,revoke_patient_access,CONSENT_PURPOSES
from .patient_portal import portal_session

router=APIRouter(prefix="/api/v1/portal",tags=["patient portal identity"])
LIFETIME_MINUTES=10
SESSION_MINUTES=30
MAX_ATTEMPTS=5

def dev_only():
    if os.getenv("APP_ENV","development").lower() not in ("development","test"):
        raise HTTPException(503,"Independent patient identity and approved OTP delivery not configured")

def hashed(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

def code_digest(id,code):
    return hmac.new(secret().encode(),(id+":"+code).encode(),hashlib.sha256).hexdigest()

def expiration(x):
    return x if x.tzinfo else x.replace(tzinfo=timezone.utc)

@router.post("/invites/{patient_id}",status_code=201)
def invite(patient_id:str,db:Session=Depends(get_db),user:User=Depends(roles("admin","operator"))):
    dev_only()
    patient=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,
        Patient.id==patient_id).with_for_update())
    if not patient:raise HTTPException(404,"Patient not found")
    if not active_consent(db,user.tenant_id,patient.id,"communication") or not active_consent(
            db,user.tenant_id,patient.id,"intake"):
        raise HTTPException(409,"Active communication and intake consent required")
    now=datetime.now(timezone.utc)
    pending=db.scalars(select(PortalLoginChallenge).where(
        PortalLoginChallenge.tenant_id==user.tenant_id,
        PortalLoginChallenge.patient_id==patient.id,
        PortalLoginChallenge.consumed_at.is_(None))).all()
    for item in pending:item.consumed_at=now
    prior=db.scalars(select(PortalAccess).where(
        PortalAccess.tenant_id==user.tenant_id,
        PortalAccess.patient_id==patient.id,PortalAccess.revoked.is_(False))).all()
    for item in prior:item.revoked=True
    invitation=secrets.token_urlsafe(40)
    code=str(secrets.randbelow(1000000)).zfill(6)
    challenge=PortalLoginChallenge(tenant_id=user.tenant_id,patient_id=patient.id,
        invitation_hash=hashed(invitation),code_hash="pending",
        expires_at=now+timedelta(minutes=LIFETIME_MINUTES),
        attempts=0,issued_by=user.id)
    db.add(challenge);db.flush()
    challenge.code_hash=code_digest(challenge.id,code)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="portal_invitation_issued_dev_only",entity_type="PortalLoginChallenge",
        entity_id=challenge.id))
    db.commit()
    return {"token":invitation,"demo_verification_code":code,"expires_in_seconds":600,
        "access_enabled":False,"independent_identity_verified":False,
        "otp_delivery":"manual_staff_demo_only",
        "warning":"Synthetic dev only. Give code separately through an authorized private channel."}

class VerifyIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    invitation_token:str=Field(min_length=35,max_length=200)
    verification_code:str=Field(pattern=r"^[0-9]{6}$")

@router.post("/session/exchange",status_code=201)
def exchange(body:VerifyIn,db:Session=Depends(get_db)):
    dev_only()
    now=datetime.now(timezone.utc)
    candidate=db.scalar(select(PortalLoginChallenge).where(
        PortalLoginChallenge.invitation_hash==hashed(body.invitation_token)))
    if not candidate:
        raise HTTPException(401,"Invalid or used invitation")
    # Lock order is patient -> challenge for issuance, revocation and exchange.
    p=db.scalar(select(Patient).where(Patient.tenant_id==candidate.tenant_id,
        Patient.id==candidate.patient_id).with_for_update())
    if not p:raise HTTPException(401,"Invalid or used invitation")
    c=db.scalar(select(PortalLoginChallenge).where(
        PortalLoginChallenge.tenant_id==candidate.tenant_id,
        PortalLoginChallenge.id==candidate.id).with_for_update())
    if not c or c.consumed_at is not None or c.attempts>=MAX_ATTEMPTS:
        raise HTTPException(401,"Invalid or used invitation")
    if expiration(c.expires_at)<=now:
        c.consumed_at=now;db.commit()
        raise HTTPException(401,"Invitation expired")
    good=hmac.compare_digest(c.code_hash,code_digest(c.id,body.verification_code))
    if not good:
        c.attempts+=1
        if c.attempts>=MAX_ATTEMPTS:c.consumed_at=now
        db.commit()
        raise HTTPException(401,"Invalid verification code")
    if not active_consent(db,c.tenant_id,c.patient_id,"intake") or not active_consent(
            db,c.tenant_id,c.patient_id,"communication"):
        c.consumed_at=now;db.commit()
        raise HTTPException(401,"Patient portal consent unavailable")
    # Only verified exchange creates a portal grant: invitation itself is powerless.
    raw=secrets.token_urlsafe(48)
    g=PortalAccess(tenant_id=c.tenant_id,patient_id=c.patient_id,
        token_hash=hashed(raw),expires_at=now+timedelta(minutes=SESSION_MINUTES),
        issued_by=c.issued_by,revoked=False)
    c.consumed_at=now
    db.add(g);db.flush()
    db.add(Audit(tenant_id=c.tenant_id,user_id=c.issued_by,
        event="patient_portal_demo_exchange",entity_type="PortalAccess",entity_id=g.id))
    db.commit()
    return {"access_token":raw,"expires_in_seconds":SESSION_MINUTES*60,
        "patient_identity_independently_verified":False,"mfa_provider_connected":False}

@router.post("/invites/revoke/{patient_id}")
def revoke(patient_id:str,db:Session=Depends(get_db),user:User=Depends(roles("admin","operator"))):
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,
        Patient.id==patient_id).with_for_update())
    if not p:raise HTTPException(404,"Patient not found")
    now=datetime.now(timezone.utc)
    grants=db.scalars(select(PortalAccess).where(
        PortalAccess.tenant_id==user.tenant_id,
        PortalAccess.patient_id==p.id,PortalAccess.revoked.is_(False))).all()
    pending=db.scalars(select(PortalLoginChallenge).where(
        PortalLoginChallenge.tenant_id==user.tenant_id,
        PortalLoginChallenge.patient_id==p.id,
        PortalLoginChallenge.consumed_at.is_(None))).all()
    for item in grants:item.revoked=True
    for item in pending:item.consumed_at=now
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="portal_access_revoked_by_staff",entity_type="Patient",entity_id=p.id))
    db.commit()
    return {"revoked":len(grants),"pending_invitations_revoked":len(pending)}

@router.post("/session/logout")
def patient_logout(x_patient_access:str|None=Header(None,alias="X-Patient-Access"),
        db:Session=Depends(get_db)):
    grant=portal_session(x_patient_access,db)
    current=db.scalar(select(PortalAccess).where(
        PortalAccess.tenant_id==grant.tenant_id,PortalAccess.id==grant.id).with_for_update())
    if not current or current.revoked:raise HTTPException(401,"Session no longer active")
    current.revoked=True
    db.add(Audit(tenant_id=current.tenant_id,user_id=current.patient_id,
        event="patient_portal_logout",entity_type="PortalAccess",entity_id=current.id))
    db.commit()
    return {"logged_out":True}

@router.get("/consents")
def consent_status(x_patient_access:str|None=Header(None,alias="X-Patient-Access"),
        db:Session=Depends(get_db)):
    g=portal_session(x_patient_access,db)
    return {"purposes":{purpose:active_consent(db,g.tenant_id,g.patient_id,purpose)
        for purpose in sorted(CONSENT_PURPOSES)},
        "independently_verified_identity":False}

class ConsentIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    purpose:str=Field(min_length=2,max_length=80)
    accepted:bool
    notice_version:str=Field(min_length=1,max_length=40)

@router.post("/consents",status_code=201)
def portal_consent(body:ConsentIn,x_patient_access:str|None=Header(None,alias="X-Patient-Access"),
        db:Session=Depends(get_db)):
    g=portal_session(x_patient_access,db)
    if body.purpose not in CONSENT_PURPOSES:raise HTTPException(422,"Unknown purpose")
    p=db.scalar(select(Patient).where(Patient.tenant_id==g.tenant_id,
        Patient.id==g.patient_id).with_for_update())
    if not p:raise HTTPException(404,"Patient not found")
    c=Consent(tenant_id=g.tenant_id,patient_id=p.id,purpose=body.purpose,
        accepted=body.accepted,notice_version=body.notice_version,
        source="patient_portal_demo")
    db.add(c);db.flush()
    if not body.accepted:
        revoke_patient_access(db,g.tenant_id,p.id,body.purpose)
    db.add(Audit(tenant_id=g.tenant_id,user_id=p.id,
        event="patient_portal_consent_granted" if body.accepted else "patient_portal_consent_withdrawn",
        entity_type="Consent",entity_id=c.id))
    db.commit()
    return {"purpose":body.purpose,"accepted":body.accepted,"recorded":True,
        "source":"patient_portal_demo","independent_identity_verified":False}
