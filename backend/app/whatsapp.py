"""Official Meta webhook: eligibility-gated, signed, idempotent and consent-aware.

No automated replies or third-party sends are performed by this adapter. Set only
with documented WhatsApp Business authorization. Unknown numbers are never
silently turned into medical cases or stored as medical message bodies.
"""
from __future__ import annotations
import os,hmac,hashlib,json
from fastapi import APIRouter,HTTPException,Request,Query,Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import select,or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import get_db
from .models import Tenant,Patient,Consent,Conversation,Message
from .enterprise_models import MessageEvent

router=APIRouter(prefix='/api/v1/webhooks/whatsapp',tags=['Official WhatsApp'])

def enabled():
    return (os.getenv('WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED','').lower()=='true'
        and os.getenv('WHATSAPP_INBOUND_PROCESSING_APPROVED','').lower()=='true'
        and all(os.getenv(k) for k in ('META_APP_SECRET','META_VERIFY_TOKEN','WHATSAPP_TENANT_SLUG','WHATSAPP_PHONE_NUMBER_ID')))

def valid_signature(payload:bytes,header:str|None,secret:str)->bool:
    if not header or not header.startswith('sha256=') or len(header)!=71:return False
    expected='sha256='+hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,header)

@router.get('',response_class=PlainTextResponse)
async def challenge(mode:str|None=Query(None,alias='hub.mode'),token:str|None=Query(None,alias='hub.verify_token'),
                    challenge_value:str|None=Query(None,alias='hub.challenge')):
    if not enabled():raise HTTPException(503,'WhatsApp disabled pending official eligibility and processing approval')
    if mode!='subscribe' or not token or not hmac.compare_digest(token,os.environ['META_VERIFY_TOKEN']):raise HTTPException(403,'Invalid verification token')
    return challenge_value or ''

@router.post('')
async def receive(request:Request,db:Session=Depends(get_db)):
    if not enabled():raise HTTPException(503,'WhatsApp disabled pending official eligibility and processing approval')
    raw=await request.body()
    if len(raw)>262144:raise HTTPException(413,'Payload too large')
    if not valid_signature(raw,request.headers.get('X-Hub-Signature-256'),os.environ['META_APP_SECRET']):raise HTTPException(403,'Invalid Meta signature')
    try:payload=json.loads(raw)
    except json.JSONDecodeError:raise HTTPException(400,'Invalid JSON')
    if payload.get('object')!='whatsapp_business_account':raise HTTPException(422,'Unsupported webhook object')
    tenant=db.scalar(select(Tenant).where(Tenant.slug==os.environ['WHATSAPP_TENANT_SLUG']))
    if not tenant:raise HTTPException(503,'Configured tenant not provisioned')
    accepted=duplicates=quarantined=0
    try:
        for entry in payload.get('entry',[]):
            for change in entry.get('changes',[]):
                if change.get('field')!='messages':continue
                value=change.get('value',{})
                account_id=value.get('metadata',{}).get('phone_number_id','')
                if account_id!=os.environ['WHATSAPP_PHONE_NUMBER_ID']:raise HTTPException(403,'Unknown WhatsApp account')
                for incoming in value.get('messages',[]):
                    mid=str(incoming.get('id',''))
                    if len(mid)<5 or len(mid)>150:continue
                    if db.scalar(select(MessageEvent.id).where(MessageEvent.tenant_id==tenant.id,
                            MessageEvent.channel=='whatsapp',MessageEvent.event_id==mid)):
                        duplicates+=1;continue
                    digest=hashlib.sha256(json.dumps(incoming,sort_keys=True).encode()).hexdigest()
                    row=MessageEvent(tenant_id=tenant.id,event_id=mid,channel='whatsapp',provider_account_id=account_id,
                                     payload_hash=digest,status='quarantined_no_matching_consent')
                    db.add(row)
                    phone=str(incoming.get('from',''))
                    patient=db.scalar(select(Patient).where(Patient.tenant_id==tenant.id,or_(Patient.contact==phone,Patient.contact=='+'+phone)))
                    # Never save a message body before an explicit, current communication consent.
                    if not patient:
                        quarantined+=1;continue
                    consent=db.scalar(select(Consent).where(Consent.tenant_id==tenant.id,Consent.patient_id==patient.id,
                            Consent.purpose=='communication').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
                    if not consent or not consent.accepted:
                        quarantined+=1;continue
                    if incoming.get('type')!='text':
                        row.status='media_requires_secure_portal';quarantined+=1;continue
                    body=str(incoming.get('text',{}).get('body',''))
                    if not body or len(body)>8000:
                        row.status='unsupported_text';quarantined+=1;continue
                    conv=db.scalar(select(Conversation).where(Conversation.tenant_id==tenant.id,
                        Conversation.patient_id==patient.id,Conversation.channel=='whatsapp').order_by(Conversation.created_at.desc()).limit(1))
                    if conv is None:
                        conv=Conversation(tenant_id=tenant.id,patient_id=patient.id,channel='whatsapp',human_handoff=True)
                        db.add(conv);db.flush()
                    db.add(Message(tenant_id=tenant.id,conversation_id=conv.id,sender='patient',language=patient.language,body=body))
                    row.status='received_for_human_review';accepted+=1
                for status in value.get('statuses',[]):
                    # Only record bounded status metadata, not raw delivery details.
                    mid='status:'+str(status.get('id',''))+':'+str(status.get('status',''))
                    if len(mid)>150 or len(mid)<15:continue
                    if not db.scalar(select(MessageEvent.id).where(MessageEvent.tenant_id==tenant.id,
                            MessageEvent.channel=='whatsapp',MessageEvent.event_id==mid)):
                        db.add(MessageEvent(tenant_id=tenant.id,event_id=mid,channel='whatsapp',
                          provider_account_id=account_id,payload_hash=hashlib.sha256(mid.encode()).hexdigest(),status='delivery_event'))
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Concurrent delivery conflict; provider may retry')
    return {'received':True,'routed_to_human':accepted,'duplicates':duplicates,'quarantined':quarantined,'auto_reply':False}
