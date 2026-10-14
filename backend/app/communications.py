"""Consent-aware messaging. Outbound WhatsApp is strictly template-based and approval-gated.

No clinical details, free-form AI output, or translations are allowed on the
WhatsApp outbound path. Messages must be reviewed before delivery.
"""
from __future__ import annotations
import os
import re
import uuid
from datetime import datetime,timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Patient, Conversation, Consent, Message, Audit
from .enterprise_models import OutboundMessage, TranslationDraft
from .security import roles
from .intake import LANGUAGES
from .ai import translate

router=APIRouter(prefix='/api/v1/communications',tags=['human-reviewed communications'])
STAFF=roles('admin','operator')
ADMIN=roles('admin')
# Only generic non-medical messaging. Templates additionally must be approved by Meta.
ALLOWED_TEMPLATES={'case_update_available','appointment_update_available','please_check_secure_portal'}

def owned(db,model,id,user):
    result=db.scalar(select(model).where(model.tenant_id==user.tenant_id,model.id==id))
    if result is None:raise HTTPException(404,'Resource not found')
    return result

def accepted(db,patient):
    c=db.scalar(select(Consent).where(Consent.tenant_id==patient.tenant_id,
        Consent.patient_id==patient.id,Consent.purpose=='communication').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    return bool(c and c.accepted)

class TranslateInput(BaseModel):
    conversation_id:str
    source_language:str
    target_language:str
    source_text:str=Field(min_length=1,max_length=3000)

@router.post('/translation-drafts',status_code=201)
def draft_translation(body:TranslateInput,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    c=owned(db,Conversation,body.conversation_id,user)
    patient=owned(db,Patient,c.patient_id,user)
    if not accepted(db,patient):raise HTTPException(409,'Communication consent required')
    if body.source_language not in LANGUAGES or body.target_language not in LANGUAGES:
        raise HTTPException(422,'Unsupported language')
    # Translation provider usage may involve sensitive text. Separate consent + approved processor.
    ai_consent=db.scalar(select(Consent).where(Consent.tenant_id==user.tenant_id,
        Consent.patient_id==patient.id,Consent.purpose=='ai_processing').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    if not ai_consent or not ai_consent.accepted:raise HTTPException(409,'AI processing consent required')
    result=translate(body.source_text,body.source_language,body.target_language)
    row=TranslationDraft(tenant_id=user.tenant_id,conversation_id=c.id,source_language=body.source_language,
         target_language=body.target_language,source_text=body.source_text,draft_text=result)
    db.add(row);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='translation_draft_created',entity_type='TranslationDraft',entity_id=row.id))
    db.commit()
    return {'id':row.id,'status':'pending_review','draft_text':row.draft_text,'target_language':row.target_language,
            'warning':'Requires human review before sending; do not interpret as medical advice'}

class ReviewTranslation(BaseModel):
    approved_text:str=Field(min_length=1,max_length=5000)
    action:str=Field(pattern='^(approve|reject)$')

@router.post('/translation-drafts/{draft_id}/review')
def review_translation(draft_id:str,body:ReviewTranslation,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    row=owned(db,TranslationDraft,draft_id,user)
    if row.status!='pending_review':raise HTTPException(409,'Translation already reviewed')
    c=owned(db,Conversation,row.conversation_id,user)
    patient=owned(db,Patient,c.patient_id,user)
    if not accepted(db,patient):raise HTTPException(409,'Communication consent required')
    row.status='approved' if body.action=='approve' else 'rejected'
    row.reviewer_id=user.id;row.reviewed_at=datetime.now(timezone.utc)
    if row.status=='approved':
        # IMPORTANT: this is an authenticated WEB-PORTAL reply, not a WhatsApp API send.
        if c.channel!='webchat':raise HTTPException(409,'Free-form WhatsApp delivery is not supported')
        db.add(Message(tenant_id=user.tenant_id,conversation_id=c.id,sender='operator',
                       language=row.target_language,body=body.approved_text))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='translation_reviewed',entity_type='TranslationDraft',entity_id=row.id))
    db.commit()
    return {'id':row.id,'status':row.status,'delivered_to_webchat':row.status=='approved'}

class OutboundInput(BaseModel):
    conversation_id:str
    template_name:str
    locale:str
    idempotency_key:str=Field(min_length=12,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')

@router.post('/outbound',status_code=201)
def create_outbound(body:OutboundInput,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    c=owned(db,Conversation,body.conversation_id,user)
    if c.channel!='whatsapp':raise HTTPException(422,'WhatsApp conversation required')
    patient=owned(db,Patient,c.patient_id,user)
    if not accepted(db,patient):raise HTTPException(409,'Communication consent required')
    if body.locale not in LANGUAGES or body.template_name not in ALLOWED_TEMPLATES:
        raise HTTPException(422,'Unsupported template or locale')
    prior=db.scalar(select(OutboundMessage).where(OutboundMessage.tenant_id==user.tenant_id,OutboundMessage.idempotency_key==body.idempotency_key))
    if prior:
        if (prior.conversation_id,prior.template_name,prior.locale)!=(c.id,body.template_name,body.locale):
            raise HTTPException(409,'Idempotency key conflict')
        return {'id':prior.id,'status':prior.status,'deduplicated':True}
    row=OutboundMessage(tenant_id=user.tenant_id,conversation_id=c.id,patient_id=patient.id,
      template_name=body.template_name,locale=body.locale,idempotency_key=body.idempotency_key)
    db.add(row);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='whatsapp_template_queued',entity_type='OutboundMessage',entity_id=row.id))
    db.commit()
    return {'id':row.id,'status':row.status,'deduplicated':False}

@router.get('/outbound')
def list_outbound(db:Session=Depends(get_db),user:User=Depends(STAFF)):
    rows=db.scalars(select(OutboundMessage).where(OutboundMessage.tenant_id==user.tenant_id).order_by(OutboundMessage.created_at.desc()).limit(100)).all()
    return [{'id':r.id,'template_name':r.template_name,'locale':r.locale,'status':r.status,'attempts':r.attempt_count} for r in rows]

@router.post('/outbound/{outbound_id}/approve')
def approve_outbound(outbound_id:str,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    row=owned(db,OutboundMessage,outbound_id,user)
    patient=owned(db,Patient,row.patient_id,user)
    if not accepted(db,patient):raise HTTPException(409,'Communication consent required')
    if row.status!='pending_approval':raise HTTPException(409,'Message already approved or processed')
    row.status='approved';row.approved_by=user.id
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='whatsapp_template_approved',entity_type='OutboundMessage',entity_id=row.id))
    db.commit()
    return {'id':row.id,'status':'approved','sent':False}
