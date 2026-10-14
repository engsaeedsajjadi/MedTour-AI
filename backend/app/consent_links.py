"""One-time patient-attested consent links (identity assurance still required for real PHI)."""
from __future__ import annotations
import hashlib,secrets,os
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .security import roles
from .models import Patient,Consent,Audit,User
from .enterprise_models import PatientConsentChallenge,PortalAccess,OutboundMessage

router=APIRouter(prefix='/api/v1/consent-links',tags=['patient attested consent'])
PURPOSES={'intake','medical_documents','communication','ai_processing'}

@router.post('/{patient_id}/{purpose}',status_code=201)
def issue(patient_id:str,purpose:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    patient=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==patient_id))
    if not patient:raise HTTPException(404,'Patient not found')
    if purpose not in PURPOSES:raise HTTPException(422,'Unknown consent purpose')
    token=secrets.token_urlsafe(40)
    c=PatientConsentChallenge(tenant_id=user.tenant_id,patient_id=patient.id,purpose=purpose,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),issued_by=user.id,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=30))
    db.add(c);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='consent_link_issued',entity_type='PatientConsentChallenge',entity_id=c.id))
    db.commit()
    return {'token':token,'purpose':purpose,'expires_in_seconds':1800,
            'notice':'Transmit only through an authorized channel; possession of link alone is not medical identity verification.'}

@router.get('/preview')
def preview(token:str=Query(min_length=35,max_length=200),db:Session=Depends(get_db)):
    challenge=db.scalar(select(PatientConsentChallenge).where(
        PatientConsentChallenge.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    if not challenge or challenge.used_at is not None:
        raise HTTPException(401,'Invalid or consumed link')
    expiry=challenge.expires_at if challenge.expires_at.tzinfo else challenge.expires_at.replace(tzinfo=timezone.utc)
    if expiry<=datetime.now(timezone.utc):raise HTTPException(401,'Expired consent link')
    return {'purpose':challenge.purpose,
            'privacy_notice_url':os.getenv('PUBLIC_PRIVACY_NOTICE_URL') or None,
            'privacy_notice_version':os.getenv('PRIVACY_NOTICE_VERSION','v0-development'),
            'production_notice_configured':bool(os.getenv('PUBLIC_PRIVACY_NOTICE_URL'))}

class Response(BaseModel):
    token:str=Field(min_length=35,max_length=200)
    notice_version:str=Field(min_length=1,max_length=40)
    accepted:bool

@router.post('/respond',status_code=201)
def respond(body:Response,db:Session=Depends(get_db)):
    if os.getenv('APP_ENV')=='production' and not os.getenv('PUBLIC_PRIVACY_NOTICE_URL'):
        raise HTTPException(503,'Production privacy notice is not configured')
    if os.getenv('APP_ENV')=='production' and body.notice_version!=os.getenv('PRIVACY_NOTICE_VERSION'):
        raise HTTPException(409,'Current privacy notice must be acknowledged')
    digest=hashlib.sha256(body.token.encode()).hexdigest()
    # Reject replay using a conditional update in the same transaction.
    c=db.scalar(select(PatientConsentChallenge).where(PatientConsentChallenge.token_hash==digest).with_for_update())
    if not c or c.used_at is not None:raise HTTPException(401,'Invalid or consumed link')
    expiry=c.expires_at if c.expires_at.tzinfo else c.expires_at.replace(tzinfo=timezone.utc)
    if expiry<=datetime.now(timezone.utc):raise HTTPException(401,'Expired consent link')
    c.used_at=datetime.now(timezone.utc)
    result=Consent(tenant_id=c.tenant_id,patient_id=c.patient_id,purpose=c.purpose,accepted=body.accepted,
         notice_version=body.notice_version,source='patient_link')
    db.add(result);db.flush()
    if not body.accepted:
        grants=db.scalars(select(PortalAccess).where(PortalAccess.tenant_id==c.tenant_id,
            PortalAccess.patient_id==c.patient_id,PortalAccess.revoked==False)).all()
        for g in grants:g.revoked=True
        msgs=db.scalars(select(OutboundMessage).where(OutboundMessage.tenant_id==c.tenant_id,
            OutboundMessage.patient_id==c.patient_id,OutboundMessage.status.in_(['pending_approval','approved']))).all()
        for m in msgs:m.status='blocked'
    db.add(Audit(tenant_id=c.tenant_id,user_id=c.patient_id,event='patient_attested_consent' if body.accepted else 'patient_withdrew_consent',
         entity_type='Consent',entity_id=result.id))
    db.commit()
    return {'purpose':c.purpose,'accepted':body.accepted,'recorded':True,'notice_version':body.notice_version,
            'source':'patient_link'}
