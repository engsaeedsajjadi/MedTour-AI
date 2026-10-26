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
from .enterprise_models import OutboundMessage
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


def _receive_delivery_status(db:Session, tenant_id:str, account_id:str, status:dict, seen:set[str])->bool:
    """Store receipt metadata only, with no automatic retry or raw provider payload."""
    if not isinstance(status,dict):return False
    state=status.get('status');provider_id=status.get('id')
    if state not in ('sent','delivered','read','failed') or not isinstance(provider_id,str) or not 5<=len(provider_id)<=160:
        return False
    digest=hashlib.sha256((provider_id+':'+state).encode('utf-8')).hexdigest()
    event_id='receipt:'+digest
    if event_id in seen or db.scalar(select(MessageEvent.id).where(
            MessageEvent.tenant_id==tenant_id,MessageEvent.channel=='whatsapp',
            MessageEvent.event_id==event_id)):
        return False
    seen.add(event_id)
    db.add(MessageEvent(tenant_id=tenant_id,channel='whatsapp',event_id=event_id,
        provider_account_id=account_id,payload_hash=digest,status='delivery_'+state))
    outbound=db.scalar(select(OutboundMessage).where(
        OutboundMessage.tenant_id==tenant_id,
        OutboundMessage.destination_channel=='whatsapp',
        OutboundMessage.provider_message_id==provider_id).with_for_update())
    if outbound:
        if state=='read' and outbound.status in ('sent','delivered'):
            outbound.status='read'
        elif state=='delivered' and outbound.status=='sent':
            outbound.status='delivered'
        elif state=='failed' and outbound.status=='sent':
            outbound.status='needs_reconciliation'
            outbound.last_error_code='PROVIDER_REPORTED_FAILURE'
    return True

@router.get('',response_class=PlainTextResponse)
async def challenge(mode:str|None=Query(None,alias='hub.mode'),token:str|None=Query(None,alias='hub.verify_token'),
                    challenge_value:str|None=Query(None,alias='hub.challenge')):
    if not enabled():raise HTTPException(503,'WhatsApp disabled pending official eligibility and processing approval')
    if mode!='subscribe' or not token or not hmac.compare_digest(token,os.environ['META_VERIFY_TOKEN']):raise HTTPException(403,'Invalid verification token')
    return challenge_value or ''

@router.post('')
async def receive(request:Request,db:Session=Depends(get_db)):
    if not enabled():raise HTTPException(503,'WhatsApp disabled pending official eligibility and processing approval')
    if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json':
        raise HTTPException(415,'JSON required')
    raw=await request.body()
    if len(raw)>262144:raise HTTPException(413,'Payload too large')
    if not valid_signature(raw,request.headers.get('X-Hub-Signature-256'),os.environ['META_APP_SECRET']):raise HTTPException(403,'Invalid Meta signature')
    try:payload=json.loads(raw)
    except json.JSONDecodeError:raise HTTPException(400,'Invalid JSON')
    if not isinstance(payload,dict) or payload.get('object')!='whatsapp_business_account':
        raise HTTPException(422,'Unsupported webhook object')
    if not isinstance(payload.get('entry',[]),list):raise HTTPException(422,'Invalid webhook entries')
    if "verified_tenant_id" in db.info:
        from types import SimpleNamespace
        # The gateway already verified the Meta HMAC and the trusted account.
        # Never read global tenants under a restricted runtime role.
        if db.info.get("verified_whatsapp_phone")!=os.environ["WHATSAPP_PHONE_NUMBER_ID"]:
            raise HTTPException(403,"Configured WhatsApp account mismatches routing identity")
        tenant=SimpleNamespace(id=db.info["verified_tenant_id"],slug=os.environ["WHATSAPP_TENANT_SLUG"])
    else:
        tenant=db.scalar(select(Tenant).where(Tenant.slug==os.environ['WHATSAPP_TENANT_SLUG']))
    if not tenant:raise HTTPException(503,'Configured tenant not provisioned')
    accepted=duplicates=quarantined=receipts=0
    seen=set()
    try:
        for entry in payload.get('entry',[]):
            if not isinstance(entry,dict) or not isinstance(entry.get('changes',[]),list):
                raise HTTPException(422,'Invalid webhook entry')
            for change in entry.get('changes',[]):
                if not isinstance(change,dict):raise HTTPException(422,'Invalid change')
                if change.get('field')!='messages':continue
                value=change.get('value',{})
                if not isinstance(value,dict) or not isinstance(value.get('metadata',{}),dict):
                    raise HTTPException(422,'Invalid webhook value')
                if not isinstance(value.get('messages',[]),list) or not isinstance(value.get('statuses',[]),list):
                    raise HTTPException(422,'Invalid webhook events')
                account_id=value.get('metadata',{}).get('phone_number_id','')
                if account_id!=os.environ['WHATSAPP_PHONE_NUMBER_ID']:raise HTTPException(403,'Unknown WhatsApp account')
                for incoming in value.get('messages',[]):
                    if not isinstance(incoming,dict):continue
                    mid=str(incoming.get('id',''))
                    if len(mid)<5 or len(mid)>150:continue
                    if mid in seen or db.scalar(select(MessageEvent.id).where(MessageEvent.tenant_id==tenant.id,
                            MessageEvent.channel=='whatsapp',MessageEvent.event_id==mid)):
                        duplicates+=1;continue
                    digest=hashlib.sha256(json.dumps(incoming,sort_keys=True).encode()).hexdigest()
                    seen.add(mid)
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
                    if _receive_delivery_status(db,tenant.id,account_id,status,seen):
                        receipts+=1
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Concurrent delivery conflict; provider may retry')
    return {'received':True,'routed_to_human':accepted,'duplicates':duplicates,'quarantined':quarantined,'receipts_processed':receipts,'auto_reply':False}
