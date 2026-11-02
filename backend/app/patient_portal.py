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
from .tenant_context import bind_tenant,system_scope
from .safety_rules import active_consent

router=APIRouter(prefix='/api/v1/portal',tags=['patient portal'])

def portal_session(token:str|None,db:Session):
    if not token or len(token)<35:raise HTTPException(401,'Patient access required')
    hashval=hashlib.sha256(token.encode()).hexdigest()
    # The secret token identifies the tenant; resolve it, then restrict the request to that tenant.
    with system_scope(db):
        owner=db.scalar(select(PortalAccess.tenant_id).where(PortalAccess.token_hash==hashval,PortalAccess.revoked==False))
    if not owner:raise HTTPException(401,'Invalid patient access')
    bind_tenant(db,owner)
    grant=db.scalar(select(PortalAccess).where(PortalAccess.token_hash==hashval,PortalAccess.revoked==False))
    if not grant:raise HTTPException(401,'Invalid patient access')
    expires=grant.expires_at
    if expires.tzinfo is None:expires=expires.replace(tzinfo=timezone.utc)
    if expires<=datetime.now(timezone.utc):raise HTTPException(401,'Patient access expired')
    if not active_consent(db,grant.tenant_id,grant.patient_id,"intake") or not active_consent(
            db,grant.tenant_id,grant.patient_id,"communication"):
        raise HTTPException(401,"Portal access consent no longer active")
    return grant

@router.get('/me')
def me(x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant=portal_session(x_patient_access,db)
    p=db.scalar(select(Patient).where(Patient.id==grant.patient_id,Patient.tenant_id==grant.tenant_id))
    if not p:raise HTTPException(404,'Patient not found')
    return {'name':p.full_name,'country':p.country,'language':p.language,'id':p.id,
            'session_expires_at':grant.expires_at,'independent_identity_assurance':False}

VISA_PENDING=('requested','in_review','ready_for_manual_submission','submission_reported')
STAY_ACTIVE=('requested','internally_held','external_request_reported','external_confirmation_reported')
TRANSFER_ACTIVE=('requested','internally_allocated','provider_contact_reported','provider_ack_reported')


def _iso(value):
    return value.isoformat() if value is not None else None


def travel_summary(db:Session,tenant_id:str,patient_id:str,case:Case,appointments:list,quotes:list)->dict:
    """Patient-safe view of the trip: statuses, dates and places only. No supplier or authority
    references, internal notes, or document numbers; each part only with its specific consent."""
    from .enterprise_models import MedicalVisa,AccommodationStay,AccommodationProperty,TravelAssignment
    visa=[];stays=[];transfers=[]
    if active_consent(db,tenant_id,patient_id,'visa_coordination'):
        for v in db.scalars(select(MedicalVisa).where(MedicalVisa.tenant_id==tenant_id,
                MedicalVisa.case_id==case.id,MedicalVisa.patient_id==patient_id,
                MedicalVisa.status.not_in(('blocked','cancelled'))).order_by(MedicalVisa.created_at)).all():
            visa.append({'status':v.status,'visa_type':v.visa_type,'decision':v.decision_reported,
                'intended_departure_at':_iso(v.intended_departure_at),
                'issued_reported':v.status=='outcome_reported' and v.decision_reported=='issued_reported'})
    if active_consent(db,tenant_id,patient_id,'accommodation_coordination'):
        rows=db.execute(select(AccommodationStay,AccommodationProperty).join(AccommodationProperty,
            (AccommodationProperty.id==AccommodationStay.property_id)&(AccommodationProperty.tenant_id==tenant_id)).where(
            AccommodationStay.tenant_id==tenant_id,AccommodationStay.case_id==case.id,
            AccommodationStay.patient_id==patient_id,AccommodationStay.status.in_(STAY_ACTIVE)).order_by(
            AccommodationStay.starts_on)).all()
        for stay,prop in rows:
            stays.append({'hotel':prop.name,'city':prop.city,'check_in':_iso(stay.starts_on),
                'check_out':_iso(stay.ends_on),'room_type':stay.room_type,'guests':stay.guests,
                'status':stay.status,'confirmed':stay.status=='external_confirmation_reported'})
    transport=active_consent(db,tenant_id,patient_id,'transport_coordination')
    interpreter=active_consent(db,tenant_id,patient_id,'interpreter_coordination')
    for t in db.scalars(select(TravelAssignment).where(TravelAssignment.tenant_id==tenant_id,
            TravelAssignment.case_id==case.id,TravelAssignment.patient_id==patient_id,
            TravelAssignment.status.in_(TRANSFER_ACTIVE)).order_by(TravelAssignment.starts_at)).all():
        if not (interpreter if t.kind=='interpreter_session' else transport):continue
        transfers.append({'kind':t.kind,'starts_at':_iso(t.starts_at),'ends_at':_iso(t.ends_at),
            'from':t.origin_zone,'to':t.destination_zone,'passengers':t.passengers,
            'language':t.language,'status':t.status,'confirmed':t.status=='provider_ack_reported'})
    pending=[]
    if not appointments:pending.append('appointment')
    if not quotes:pending.append('quote')
    if any(not v['issued_reported'] for v in visa):pending.append('visa')
    if not stays or any(not x['confirmed'] for x in stays):pending.append('accommodation')
    if any(not x['confirmed'] for x in transfers):pending.append('transfer')
    if case.status not in ('travel_planning','arrived','in_treatment','follow_up'):pending.append('case_approval')
    first_departure=next((v['intended_departure_at'] for v in visa if v['intended_departure_at']),None)
    return {'visa':visa,'accommodation':stays,'transfers':transfers,
        'readiness':{'ready_to_travel':not pending,'pending':pending,
            'departure_at':first_departure,
            # Statuses are reported by staff; the patient must keep the originals from each provider.
            'confirmations_independently_verified':False}}


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
            'approved_quotes':[{'amount_minor':q.amount_minor,'currency':q.currency,'id':q.id} for q in quotes],
            'travel':travel_summary(db,grant.tenant_id,grant.patient_id,c,appts,quotes)})
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
