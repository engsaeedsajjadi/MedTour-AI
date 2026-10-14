"""Conservative explicit outbound worker.

A message is marked `sending` BEFORE the external API call. A crash after that
is NOT automatically retried, avoiding silent duplicate contact with patients.
Operators must reconcile ambiguous sends with the provider manually.
"""
from __future__ import annotations
import os,sys
from datetime import datetime,timezone
from sqlalchemy import select
from .database import SessionLocal
from .models import Patient, Consent, Audit
from .enterprise_models import OutboundMessage
from .communications import ALLOWED_TEMPLATES

LANG_MAP={'fa':'fa','ar':'ar','en':'en_US','ps':'ps','prs':'fa_AF'}

def enabled():
    from .whatsapp import enabled as webhook_enabled
    return webhook_enabled() and os.getenv('WHATSAPP_OUTBOUND_APPROVED','').lower()=='true' and bool(os.getenv('META_ACCESS_TOKEN'))

def send_one(outbound_id:str)->dict:
    if not enabled():return {'status':'blocked','reason':'Provider eligibility/outbound processing not approved'}
    with SessionLocal() as db:
        msg=db.scalar(select(OutboundMessage).where(OutboundMessage.id==outbound_id))
        if not msg:return {'status':'not_found'}
        if msg.status!='approved':return {'status':'not_approved'}
        p=db.scalar(select(Patient).where(Patient.id==msg.patient_id,Patient.tenant_id==msg.tenant_id))
        c=db.scalar(select(Consent).where(Consent.tenant_id==msg.tenant_id,Consent.patient_id==msg.patient_id,
            Consent.purpose=='communication').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
        if not p or not c or not c.accepted or msg.template_name not in ALLOWED_TEMPLATES or msg.locale not in LANG_MAP:
            msg.status='blocked';db.commit();return {'status':'blocked','reason':'Consent or template invalid'}
        e164=p.contact.lstrip('+')
        if not e164.isdigit() or len(e164)<8 or len(e164)>15:
            msg.status='blocked';db.commit();return {'status':'blocked','reason':'Invalid international phone'}
        msg.status='sending';msg.attempt_count+=1;db.commit()
        phone=e164;template=msg.template_name;locale=LANG_MAP[msg.locale]
    import httpx
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            result=client.post('https://graph.facebook.com/'+os.getenv('META_API_VERSION','v23.0')+'/'+os.environ['WHATSAPP_PHONE_NUMBER_ID']+'/messages',
                headers={'Authorization':'Bearer '+os.environ['META_ACCESS_TOKEN']},json={
                    'messaging_product':'whatsapp','to':phone,'type':'template',
                    'template':{'name':template,'language':{'code':locale}}})
            result.raise_for_status()
            provider_id=result.json()['messages'][0]['id']
        if not isinstance(provider_id,str) or not provider_id:raise ValueError('Invalid provider response')
    except Exception:
        # Ambiguous network outcome: manual reconciliation instead of automatic retry.
        with SessionLocal() as db:
            msg=db.scalar(select(OutboundMessage).where(OutboundMessage.id==outbound_id))
            if msg and msg.status=='sending':msg.status='needs_reconciliation';msg.last_error_code='PROVIDER_OUTCOME_UNKNOWN';db.commit()
        return {'status':'needs_reconciliation'}
    with SessionLocal() as db:
        msg=db.scalar(select(OutboundMessage).where(OutboundMessage.id==outbound_id))
        if msg and msg.status=='sending':
            msg.status='sent';msg.provider_message_id=provider_id;msg.sent_at=datetime.now(timezone.utc)
            db.add(Audit(tenant_id=msg.tenant_id,user_id=msg.approved_by or '',event='whatsapp_template_sent',
                entity_type='OutboundMessage',entity_id=msg.id));db.commit()
    return {'status':'sent'}

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python -m app.delivery <approved-outbound-id>')
    print(send_one(sys.argv[1]))
