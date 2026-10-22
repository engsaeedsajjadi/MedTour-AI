"""Short-lived patient access links. Do not put tokens into logs or analytics."""
from __future__ import annotations
import hashlib,secrets
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Header
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Patient,Case,Appointment,Quote,TravelRequest,Consent,User,Audit
from .enterprise_models import PortalAccess,Operation
from .security import roles

router=APIRouter(prefix='/api/v1/portal',tags=['patient portal'])

def portal_session(token:str|None,db:Session):
    if not token or len(token)<35:raise HTTPException(401,'Patient access required')
    hashval=hashlib.sha256(token.encode()).hexdigest()
    grant=db.scalar(select(PortalAccess).where(PortalAccess.token_hash==hashval,PortalAccess.revoked==False))
    if not grant:raise HTTPException(401,'Invalid patient access')
    expires=grant.expires_at
    if expires.tzinfo is None:expires=expires.replace(tzinfo=timezone.utc)
    if expires<=datetime.now(timezone.utc):raise HTTPException(401,'Patient access expired')
    return grant

@router.post('/invites/{patient_id}',status_code=201)
def invite(patient_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    p=db.scalar(select(Patient).where(Patient.id==patient_id,Patient.tenant_id==user.tenant_id))
    if not p:raise HTTPException(404,'Patient not found')
    consent=db.scalar(select(Consent).where(Consent.patient_id==p.id,Consent.tenant_id==user.tenant_id,
        Consent.purpose=='communication').order_by(Consent.created_at.desc()).limit(1))
    if not consent or not consent.accepted:raise HTTPException(409,'Communication consent required')
    token=secrets.token_urlsafe(36)
    grant=PortalAccess(tenant_id=user.tenant_id,patient_id=p.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc)+timedelta(hours=2),issued_by=user.id)
    db.add(grant);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='patient_portal_invite_issued',entity_type='Patient',entity_id=p.id))
    db.commit()
    # Operator must pass link over an approved channel. Token returned only at creation.
    return {'token':token,'expires_in_seconds':7200,'warning':'Single-purpose time-limited access. Share only via an approved private channel.'}

@router.post('/invites/revoke/{patient_id}')
def revoke(patient_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    p=db.scalar(select(Patient).where(Patient.id==patient_id,Patient.tenant_id==user.tenant_id))
    if not p:raise HTTPException(404,'Patient not found')
    gs=db.scalars(select(PortalAccess).where(PortalAccess.tenant_id==user.tenant_id,PortalAccess.patient_id==p.id,PortalAccess.revoked==False)).all()
    for g in gs:g.revoked=True
    db.commit();return {'revoked':len(gs)}

@router.get('/me')
def me(x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant=portal_session(x_patient_access,db)
    p=db.scalar(select(Patient).where(Patient.id==grant.patient_id,Patient.tenant_id==grant.tenant_id))
    if not p:raise HTTPException(404,'Patient not found')
    return {'name':p.full_name,'country':p.country,'language':p.language,'id':p.id}

@router.get('/journey')
def journey(x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant=portal_session(x_patient_access,db)
    cases=db.scalars(select(Case).where(Case.tenant_id==grant.tenant_id,Case.patient_id==grant.patient_id)).all()
    data=[]
    for c in cases:
        # Only administrative service state is exposed to the patient, no clinician internal notes.
        ops=db.scalars(select(Operation).where(Operation.tenant_id==grant.tenant_id,Operation.case_id==c.id)).all()
        appts=db.scalars(select(Appointment).where(Appointment.tenant_id==grant.tenant_id,Appointment.case_id==c.id,Appointment.status=='confirmed')).all()
        quotes=db.scalars(select(Quote).where(Quote.tenant_id==grant.tenant_id,Quote.case_id==c.id,Quote.status=='approved')).all()
        data.append({'case_id':c.id,'specialty':c.specialty,'status':c.status,
            'services':[{'service':o.kind,'status':o.status} for o in ops],
            'confirmed_appointments':[{'at':a.requested_at,'reference':a.confirmation_reference} for a in appts],
            'approved_quotes':[{'amount_minor':q.amount_minor,'currency':q.currency,'id':q.id} for q in quotes]})
    return data

class PatientMessageIn(BaseModel):
    message:str=Field(min_length=1,max_length=4000)
    language:str|None=None

@router.post('/chat',status_code=201)
def patient_chat(body:PatientMessageIn,x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    from .models import Conversation,Message
    from .intake import LANGUAGES
    from .receptionist import receptionist_response
    grant=portal_session(x_patient_access,db)
    p=db.scalar(select(Patient).where(Patient.id==grant.patient_id,Patient.tenant_id==grant.tenant_id))
    lang=body.language or p.language
    if lang not in LANGUAGES:raise HTTPException(422,'Unsupported language')
    consent=db.scalar(select(Consent).where(Consent.tenant_id==grant.tenant_id,Consent.patient_id==p.id,
            Consent.purpose=='communication').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    if not consent or not consent.accepted:raise HTTPException(409,'Communication consent required')
    x=db.scalar(select(Conversation).where(Conversation.tenant_id==grant.tenant_id,Conversation.patient_id==p.id,
                         Conversation.channel=='webchat').order_by(Conversation.created_at.desc()).limit(1))
    if not x:
        x=Conversation(tenant_id=grant.tenant_id,patient_id=p.id,channel='webchat')
        db.add(x);db.flush()
    safety=receptionist_response(lang,body.message)
    from .human_inbox import inbound_webchat
    db.add(Message(tenant_id=grant.tenant_id,conversation_id=x.id,sender='patient',body=body.message,language=lang))
    if safety['human_handoff_required']:
        x.human_handoff=True
    inbound_webchat(db,x,urgent=safety['emergency_keyword_detected'])
    # A deterministic safety response is issued; LLM is never trusted to make a medical decision.
    if not x.human_handoff:
        db.add(Message(tenant_id=grant.tenant_id,conversation_id=x.id,sender='assistant',body=safety['message'],language=lang))
    db.commit()
    return {'conversation_id':x.id,'automated_response':None if x.human_handoff else safety['message'],
            'warning':safety['message'] if safety['emergency_keyword_detected'] else None,
            'handoff_notice':safety['message'] if safety['human_handoff_required'] else None,
            'language':lang,'intent':safety['intent'],
            'human_handoff':x.human_handoff,'requires_human_review':True,
            'automated_clinical_decision':False}

@router.get('/chat')
def patient_chat_history(x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    from .models import Conversation,Message
    grant=portal_session(x_patient_access,db)
    x=db.scalar(select(Conversation).where(Conversation.tenant_id==grant.tenant_id,
        Conversation.patient_id==grant.patient_id,Conversation.channel=='webchat').order_by(Conversation.created_at.desc()).limit(1))
    if not x:return []
    messages=db.scalars(select(Message).where(Message.tenant_id==grant.tenant_id,
                 Message.conversation_id==x.id).order_by(Message.created_at.asc()).limit(100)).all()
    return [{'sender':m.sender,'language':m.language,'body':m.body,'created_at':m.created_at} for m in messages]
