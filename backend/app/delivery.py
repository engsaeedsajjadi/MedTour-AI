"""Explicitly approved WhatsApp template dispatch, never clinical automation.

The durable SQL outbox is the source of truth. A conditional atomic claim avoids
double sending when several worker processes poll the same approved row. Any
ambiguous external delivery outcome requires manual reconciliation, not retry.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from sqlalchemy import select, update
from .database import SessionLocal
from .models import Patient, Consent, Audit
from .enterprise_models import OutboundMessage
from .communications import ALLOWED_TEMPLATES

LANG_MAP = {'fa':'fa','ar':'ar','en':'en_US','ps':'ps','prs':'fa_AF'}


def enabled() -> bool:
    from .whatsapp import enabled as webhook_enabled
    return bool(
        os.getenv('APP_ENV', 'development').lower() != 'production'
        and webhook_enabled()
        and os.getenv('WHATSAPP_OUTBOUND_APPROVED', '').lower() == 'true'
        and os.getenv('META_ACCESS_TOKEN')
        and re.fullmatch(r'[0-9]{4,32}', os.getenv('WHATSAPP_PHONE_NUMBER_ID',''))
        and re.fullmatch(r'v[0-9]{1,2}\.[0-9]{1,2}', os.getenv('META_API_VERSION','v23.0'))
    )


def send_one(outbound_id: str, *, tenant_session_factory=None,
             expected_tenant_id: str | None = None) -> dict:
    if (tenant_session_factory is None) != (expected_tenant_id is None):
        raise ValueError("Bounded tenant dispatch requires both trusted factory and tenant ID")
    if os.getenv("TENANT_DB_ROUTING_MODE") == "strict" and tenant_session_factory is None:
        return {"status":"blocked","reason":"Shared runtime DB forbidden in strict tenant mode"}
    make_session=tenant_session_factory or SessionLocal
    if not enabled():
        return {'status':'blocked','reason':'Provider eligibility/outbound processing not approved'}
    with make_session() as db:
        # Locks the row on PostgreSQL; the conditional UPDATE below also
        # protects the claim when a database ignores SELECT FOR UPDATE.
        predicates=[OutboundMessage.id == outbound_id]
        if expected_tenant_id is not None:
            predicates.append(OutboundMessage.tenant_id == expected_tenant_id)
        msg = db.scalar(select(OutboundMessage).where(*predicates).with_for_update())
        if not msg:
            return {'status':'not_found'}
        if msg.status != 'approved':
            return {'status':'not_approved'}

        patient = db.scalar(select(Patient).where(
            Patient.id == msg.patient_id,
            Patient.tenant_id == msg.tenant_id,
        ))
        consent = db.scalar(select(Consent).where(
            Consent.tenant_id == msg.tenant_id,
            Consent.patient_id == msg.patient_id,
            Consent.purpose == 'communication',
        ).order_by(Consent.created_at.desc(), Consent.id.desc()).limit(1))
        if (not patient or not consent or not consent.accepted or not msg.approved_by
                or msg.template_name not in ALLOWED_TEMPLATES
                or msg.locale not in LANG_MAP):
            msg.status = 'blocked'
            db.commit()
            return {'status':'blocked','reason':'Consent, approval or template invalid'}

        phone = patient.contact.lstrip('+')
        if not phone.isdigit() or not 8 <= len(phone) <= 15:
            msg.status = 'blocked'
            db.commit()
            return {'status':'blocked','reason':'Invalid international phone'}

        claim = db.execute(update(OutboundMessage).where(
            OutboundMessage.id == outbound_id,
            OutboundMessage.tenant_id == msg.tenant_id,
            OutboundMessage.status == 'approved',
        ).values(
            status='sending',
            attempt_count=OutboundMessage.attempt_count + 1,
        ).execution_options(synchronize_session=False))
        if claim.rowcount != 1:
            db.rollback()
            return {'status':'not_approved'}
        template = msg.template_name
        locale = LANG_MAP[msg.locale]
        db.commit()

    # The only external network request. No PHI/free-text in the template.
    import httpx
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(
                'https://graph.facebook.com/' + os.getenv('META_API_VERSION', 'v23.0')
                + '/' + os.environ['WHATSAPP_PHONE_NUMBER_ID'] + '/messages',
                headers={'Authorization':'Bearer ' + os.environ['META_ACCESS_TOKEN']},
                json={
                    'messaging_product':'whatsapp',
                    'to':phone,
                    'type':'template',
                    'template':{'name':template, 'language':{'code':locale}},
                }
            )
            response.raise_for_status()
            provider_id = response.json()['messages'][0]['id']
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError('Invalid provider response')
    except Exception:
        # A timeout may mean the provider DID send. Never retry automatically.
        with SessionLocal() as db:
            db.execute(update(OutboundMessage).where(
                OutboundMessage.id == outbound_id,
                OutboundMessage.tenant_id == expected_tenant_id if expected_tenant_id is not None else OutboundMessage.tenant_id == OutboundMessage.tenant_id,
                OutboundMessage.status == 'sending'
            ).values(status='needs_reconciliation', last_error_code='PROVIDER_OUTCOME_UNKNOWN'))
            db.commit()
        return {'status':'needs_reconciliation'}

    with SessionLocal() as db:
        row = db.scalar(select(OutboundMessage).where(
            OutboundMessage.id == outbound_id,
            OutboundMessage.tenant_id == expected_tenant_id if expected_tenant_id is not None else OutboundMessage.tenant_id == OutboundMessage.tenant_id
        ).with_for_update())
        if row and row.status == 'sending':
            row.status = 'sent'
            row.provider_message_id = provider_id
            row.sent_at = datetime.now(timezone.utc)
            db.add(Audit(
                tenant_id=row.tenant_id,
                user_id=row.approved_by or '',
                event='whatsapp_template_sent',
                entity_type='OutboundMessage',
                entity_id=row.id,
            ))
            db.commit()
            return {'status':'sent'}
        # External send can succeed after a consent withdrawal or a concurrent
        # state change: NEVER claim success internally. Operator must reconcile.
        db.rollback()
        return {'status':'needs_reconciliation'}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m app.delivery <approved-outbound-id>')
    print(send_one(sys.argv[1]))
