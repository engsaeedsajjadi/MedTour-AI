from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from . import enterprise_models  # register enterprise tables
from .database import get_db
from .models import (User,Tenant,Patient,Case,Consent,Document,Physician,Hospital,Referral,
                     Appointment,Quote,TravelRequest,Conversation,Message,Task,Audit)
from .security import current_user,roles,password_verify,token_for
from .intake import intake_response, PROMPTS, LANGUAGES, IntakeAnswer
from .ai import draft as ai_draft, provider_available
from .whatsapp import router as whatsapp_router
from .telegram import router as telegram_router, enabled as telegram_enabled
from .rate_limit import throttle
from .safety_rules import assert_safe_runtime, public_safety_contract, revoke_patient_access
assert_safe_runtime()

app=FastAPI(title='MedTour AI Coordination API',version='0.5.0-alpha',description='Development foundation. Not approved for production PHI or clinical care.')
app.include_router(whatsapp_router)
app.include_router(telegram_router)
origins=[p.strip() for p in os.getenv('CORS_ORIGINS','http://localhost:3000').split(',') if p.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=['GET','POST','PATCH','PUT'],allow_headers=['Authorization','Content-Type','X-Patient-Access'])

ROLES = ('admin','operator','physician','patient','auditor')
MODERATOR = roles('admin','operator')
MANAGER = roles('admin')
CASES = {'new','intake','documents_pending','review_pending','provider_review','quote_pending','quote_sent','confirmed','travel_planning','arrived','in_treatment','follow_up','closed','cancelled'}
TRANSITIONS = {'new':{'intake','cancelled'},'intake':{'documents_pending','review_pending','cancelled'},
 'documents_pending':{'review_pending','cancelled'},'review_pending':{'provider_review','cancelled'},
 'provider_review':{'quote_pending','cancelled'},'quote_pending':{'quote_sent','cancelled'},
 'quote_sent':{'confirmed','quote_pending','cancelled'},'confirmed':{'travel_planning','cancelled'},
 'travel_planning':{'arrived','cancelled'},'arrived':{'in_treatment','cancelled'},
 'in_treatment':{'follow_up'},'follow_up':{'closed'},'closed':set(),'cancelled':set()}
TRAVEL_TYPES={'visa','hotel','transport','interpreter','home_visit'}

class LoginIn(BaseModel):
    tenant_slug:str
    email:str
    password:str
    totp_code:str|None=None
class PatientIn(BaseModel):
    full_name:str=Field(min_length=2,max_length=200)
    country:str=Field(max_length=100,default='')
    language:str='en'
    contact:str=Field(max_length=200,default='')
class CaseIn(BaseModel):
    patient_id:str
    complaint:str=Field(default='',max_length=5000)
    specialty:str=Field(default='',max_length=100)
class CaseStatusIn(BaseModel):
    status:str
    reference:str|None=Field(default=None,min_length=6,max_length=100,pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$')
class ConsentIn(BaseModel):
    patient_id:str
    purpose:Literal['intake','medical_documents','communication','ai_processing','hospital_coordination' ,'visa_coordination','accommodation_coordination','transport_coordination','interpreter_coordination','agent_referral']
    accepted:bool
    notice_version:str=Field(min_length=1,max_length=40)
class PhysicianIn(BaseModel):
    full_name:str=Field(min_length=2,max_length=200)
    specialty:str=Field(min_length=2,max_length=120)
    city:str=Field(default='',max_length=100)
class HospitalIn(BaseModel):
    name:str=Field(min_length=2,max_length=200)
    city:str=Field(default='',max_length=100)
class StatusIn(BaseModel):
    status:str
    reference:str|None=None
class ReferralIn(BaseModel):
    case_id:str
    physician_id:str
class QuoteIn(BaseModel):
    case_id:str
    currency:str=Field(min_length=3,max_length=3)
    amount_minor:int=Field(ge=0,le=10**15)
    details:str=Field(default='',max_length=8000)
class AppointmentIn(BaseModel):
    case_id:str
    physician_id:str
    requested_at:datetime
class TravelIn(BaseModel):
    case_id:str
    service_type:str
    notes:str=Field(default='',max_length=3000)
class ConversationIn(BaseModel):
    patient_id:str
class MessageIn(BaseModel):
    body:str=Field(min_length=1,max_length=8000)
    language:str='en'
class DocumentIn(BaseModel):
    patient_id:str
    case_id:str
    filename:str=Field(min_length=1,max_length=255)
    category:str=Field(default='report',max_length=70)
class AIDraftIn(BaseModel):
    case_id:str
    language:str=Field(default="en")
    message:str=Field(min_length=1,max_length=3000)
class TaskIn(BaseModel):
    case_id:str
    title:str=Field(min_length=3,max_length=200)

def require_owned(db:Session,model,pk:str,user:User):
    obj=db.scalar(select(model).where(model.id==pk,model.tenant_id==user.tenant_id))
    if not obj: raise HTTPException(status_code=404,detail='Not found')
    return obj

def listed(db:Session,model,user:User,limit:int):
    return list(db.scalars(select(model).where(model.tenant_id==user.tenant_id).order_by(model.created_at.desc()).limit(limit)).all())

def audit(db:Session,user:User,event:str,obj):
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event=event,entity_type=type(obj).__name__,entity_id=obj.id))

def save(db:Session,user:User,obj,event:str):
    db.add(obj); db.flush(); audit(db,user,event,obj);db.commit();db.refresh(obj)
    return public(obj)

def public(obj):
    # Model allow-list to avoid accidental password hash exposure.
    allowed={
        Patient:['id','full_name','country','language','contact','created_at'],
        Case:['id','patient_id','complaint','specialty','status','assigned_operator_id','created_at'],
        Consent:['id','patient_id','purpose','accepted','notice_version','source','created_at'],
        Document:['id','patient_id','case_id','filename','category','status','created_at'],
        Physician:['id','full_name','specialty','city','credential_status','created_at'],
        Hospital:['id','name','city','license_status','created_at'],
        Referral:['id','case_id','physician_id','status','reviewer_note','created_at'],
        Quote:['id','case_id','currency','amount_minor','details','status','approved_by','created_at'],
        Appointment:['id','case_id','physician_id','requested_at','status','confirmation_reference','created_at'],
        TravelRequest:['id','case_id','service_type','status','notes','external_reference','created_at'],
        Conversation:['id','patient_id','channel','human_handoff','assigned_user_id','created_at'],
        Message:['id','conversation_id','sender','language','body','created_at'],
        Task:['id','case_id','title','status','created_at'],
        Audit:['id','user_id','event','entity_type','entity_id','created_at'],
    }
    return {key:getattr(obj,key) for key in allowed[type(obj)]}

def need_consent(db:Session,user:User,patient_id:str,purpose:str):
    last=db.scalar(select(Consent).where(Consent.tenant_id==user.tenant_id,Consent.patient_id==patient_id,Consent.purpose==purpose).order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    if not last or not last.accepted:raise HTTPException(status_code=409,detail=f'Active {purpose} consent required')

def require_case(db:Session,user:User,case_id:str):
    return require_owned(db,Case,case_id,user)

def require_provider(db:Session,user:User,physician_id:str):
    physician=require_owned(db,Physician,physician_id,user)
    if physician.credential_status!='verified': raise HTTPException(409,'Physician must be manually verified first')
    return physician

@app.middleware('http')
async def security_headers(request:Request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    if os.getenv('APP_ENV')=='production':
        response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.get('/api/v1/safety/contract')
def safety_contract():
    return public_safety_contract()

@app.get('/api/v1/health/live')
def health(): return {'status':'live','phase':'development','production_ready':False}

@app.get('/api/v1/health/ready')
def ready(db:Session=Depends(get_db)):
    from .stack_health import probe_stack
    try:
        return probe_stack(db)
    except Exception as exc:
        raise HTTPException(503,'Required stack dependency unavailable') from exc


@app.post('/api/v1/auth/login')
def login(body:LoginIn,request:Request,db:Session=Depends(get_db)):
    throttle((request.client.host if request.client else 'unknown')+':'+body.tenant_slug+':'+body.email.lower().strip())
    tenant=db.scalar(select(Tenant).where(Tenant.slug==body.tenant_slug))
    if not tenant:raise HTTPException(401,'Invalid credentials')
    user=db.scalar(select(User).where(User.tenant_id==tenant.id,User.email==body.email.lower().strip(),User.active==True))
    if not user or not password_verify(body.password,user.password_hash):raise HTTPException(401,'Invalid credentials')
    from .staff_mfa import ensure_enrolled_gate
    ensure_enrolled_gate(db,user,body.totp_code)
    from .session_api import issue_refresh
    from .staff_mfa import row_for
    enrollment=row_for(db,user.tenant_id,user.id)
    assured=bool(enrollment and enrollment.enabled)
    return {'access_token':token_for(user,mfa_verified=assured),'refresh_token':issue_refresh(db,user),'token_type':'bearer','role':user.role,'tenant_id':user.tenant_id}

@app.get('/api/v1/auth/me')
def me(user:User=Depends(current_user)):
    return {'id':user.id,'email':user.email,'role':user.role,'tenant_id':user.tenant_id}

@app.get('/api/v1/dashboard')
def dashboard(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    models={'patients':Patient,'cases':Case,'physicians':Physician,'hospitals':Hospital,'quotes':Quote,'travel_requests':TravelRequest,'conversations':Conversation}
    return {key:db.scalar(select(func.count()).select_from(model).where(model.tenant_id==user.tenant_id)) for key,model in models.items()}

@app.get('/api/v1/patients')
def patients(limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Patient,user,limit)]
@app.post('/api/v1/patients',status_code=201)
def create_patient(body:PatientIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    if body.language not in LANGUAGES:raise HTTPException(422,'Unsupported language')
    import re
    supplied=body.model_dump()
    cleaned=body.contact.strip()
    # Normalize phone-like contacts to a canonical digit-only international identifier.
    if re.fullmatch(r'\+?[\d ()-]{8,25}',cleaned):
        cleaned=''.join(c for c in cleaned if c.isdigit())
    supplied['contact']=cleaned
    return save(db,user,Patient(tenant_id=user.tenant_id,**supplied),'patient_created')

@app.get('/api/v1/patients/{patient_id}')
def patient_detail(patient_id:str,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return public(require_owned(db,Patient,patient_id,user))

@app.post('/api/v1/consents',status_code=201)
def consent(body:ConsentIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_owned(db,Patient,body.patient_id,user)
    row=Consent(tenant_id=user.tenant_id,**body.model_dump())
    db.add(row);db.flush()
    if not body.accepted:
        revoke_patient_access(db,user.tenant_id,body.patient_id,body.purpose)
    audit(db,user,'consent_recorded' if body.accepted else 'consent_withdrawn',row)
    db.commit();db.refresh(row)
    return public(row)

@app.get('/api/v1/cases')
def cases(limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Case,user,limit)]
@app.post('/api/v1/cases',status_code=201)
def create_case(body:CaseIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_owned(db,Patient,body.patient_id,user)
    need_consent(db,user,body.patient_id,'intake')
    return save(db,user,Case(tenant_id=user.tenant_id,**body.model_dump()),'case_created')
@app.get('/api/v1/cases/{case_id}')
def case_detail(case_id:str,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return public(require_case(db,user,case_id))
@app.patch('/api/v1/cases/{case_id}/status')
def case_status(case_id:str,body:CaseStatusIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    c=require_case(db,user,case_id)
    if body.status not in TRANSITIONS.get(c.status,set()):raise HTTPException(409,'Invalid case workflow transition')
    from .case_mission import check_mission_transition
    from .enterprise_models import CaseTimeline
    check_mission_transition(db,c,body.status,user.role,body.reference)
    previous=c.status
    c.status=body.status
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=c.id,actor_id=user.id,
                        event='case_status_transition',
                        details=f'{previous}->{body.status};evidence={body.reference or "not-required"}'))
    return save(db,user,c,'case_status_changed')

@app.get('/api/v1/intake/prompts/{language}')
def prompts(language:str,user:User=Depends(MODERATOR)):
    if language not in LANGUAGES:raise HTTPException(404,'Unsupported language')
    return {'language':language,'prompts':PROMPTS[language]}
@app.post('/api/v1/intake/evaluate')
def intake(body:IntakeAnswer,user:User=Depends(MODERATOR)):
    return intake_response(body.language,body.message)

@app.post('/api/v1/intake/ai-draft')
def intake_ai(body:AIDraftIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    c=require_case(db,user,body.case_id)
    need_consent(db,user,c.patient_id,'ai_processing')
    if body.language not in LANGUAGES:raise HTTPException(422,'Unsupported language')
    # Neither urgent messages nor explicit human requests may reach the LLM.
    from .receptionist import receptionist_response
    safety=receptionist_response(body.language,body.message)
    if safety['human_handoff_required']:return safety
    return ai_draft(body.message,body.language)

@app.get('/api/v1/physicians')
def physicians(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Physician,user,200)]
@app.post('/api/v1/physicians',status_code=201)
def physician(body:PhysicianIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return save(db,user,Physician(tenant_id=user.tenant_id,**body.model_dump()),'physician_created')
@app.patch('/api/v1/physicians/{id}/verification')
def physician_verify(id:str,body:StatusIn,db:Session=Depends(get_db),user:User=Depends(MANAGER)):
    p=require_owned(db,Physician,id,user)
    if body.status not in ('verified','unverified','rejected'):raise HTTPException(422,'Bad status')
    p.credential_status=body.status
    return save(db,user,p,'physician_verification_changed')

@app.get('/api/v1/hospitals')
def hospitals(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Hospital,user,200)]
@app.post('/api/v1/hospitals',status_code=201)
def hospital(body:HospitalIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return save(db,user,Hospital(tenant_id=user.tenant_id,**body.model_dump()),'hospital_created')
@app.patch('/api/v1/hospitals/{id}/verification')
def hospital_verify(id:str,body:StatusIn,db:Session=Depends(get_db),user:User=Depends(MANAGER)):
    h=require_owned(db,Hospital,id,user)
    if body.status not in ('verified','unverified','rejected'):raise HTTPException(422,'Bad status')
    h.license_status=body.status
    return save(db,user,h,'hospital_verification_changed')

@app.get('/api/v1/referrals')
def referrals(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Referral,user,200)]
@app.post('/api/v1/referrals',status_code=201)
def refer(body:ReferralIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_case(db,user,body.case_id);require_provider(db,user,body.physician_id)
    return save(db,user,Referral(tenant_id=user.tenant_id,**body.model_dump()),'referral_requested')
@app.patch('/api/v1/referrals/{id}/status')
def referral_status(id:str,body:StatusIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    r=require_owned(db,Referral,id,user)
    if body.status not in ('approved','declined') or r.status!='requested':raise HTTPException(409,'Invalid referral state')
    r.status=body.status
    return save(db,user,r,'referral_reviewed')

@app.get('/api/v1/quotes')
def quotes(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Quote,user,200)]
@app.post('/api/v1/quotes',status_code=201)
def quote(body:QuoteIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_case(db,user,body.case_id)
    if not body.currency.isascii() or not body.currency.isalpha():raise HTTPException(422,'Use ISO currency code')
    return save(db,user,Quote(tenant_id=user.tenant_id,**body.model_dump(exclude={'currency'}),currency=body.currency.upper()),'quote_drafted')
@app.patch('/api/v1/quotes/{id}/approve')
def approve_quote(id:str,db:Session=Depends(get_db),user:User=Depends(MANAGER)):
    q=require_owned(db,Quote,id,user)
    if q.status!='draft':raise HTTPException(409,'Only draft quotes can be approved')
    from .enterprise_models import QuoteVersion
    version=db.scalar(select(QuoteVersion).where(QuoteVersion.tenant_id==user.tenant_id,
        QuoteVersion.quote_id==q.id).limit(1))
    if version is not None:raise HTTPException(409,'Use quotation-versions approval workflow')
    q.status='approved';q.approved_by=user.id
    return save(db,user,q,'quote_approved')

@app.get('/api/v1/appointments')
def appointments(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Appointment,user,200)]
@app.post('/api/v1/appointments',status_code=201)
def appointment(body:AppointmentIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_case(db,user,body.case_id);require_provider(db,user,body.physician_id)
    if body.requested_at.tzinfo is None:raise HTTPException(422,'Timezone offset required')
    dt=body.requested_at.astimezone(timezone.utc)
    if dt < datetime.now(timezone.utc):raise HTTPException(422,'Appointment must be in the future')
    # Legacy API records administrative requests only; it must not race with
    # conflict-safe calendar allocations or imply reserved resources.
    from .enterprise_models import AppointmentSlot
    from .safety_rules import active_consent
    c=require_case(db,user,body.case_id)
    if not active_consent(db,user.tenant_id,c.patient_id,'intake'):
        raise HTTPException(409,'Active intake consent required')
    return save(db,user,Appointment(tenant_id=user.tenant_id,case_id=body.case_id,physician_id=body.physician_id,requested_at=dt),'appointment_requested')
@app.patch('/api/v1/appointments/{id}/status')
def appointment_status(id:str,body:StatusIn,db:Session=Depends(get_db),user:User=Depends(MANAGER)):
    a=require_owned(db,Appointment,id,user)
    if a.status!='requested' or body.status not in ('confirmed','cancelled'):raise HTTPException(409,'Invalid appointment state')
    if body.status=='confirmed' and not body.reference:raise HTTPException(422,'Independent provider confirmation reference required')
    from .enterprise_models import AppointmentSlot
    managed=db.scalar(select(AppointmentSlot).where(
        AppointmentSlot.tenant_id==user.tenant_id,
        AppointmentSlot.appointment_id==a.id))
    if managed:raise HTTPException(409,'Use the appointment-calendar review workflow')
    a.status=body.status;a.confirmation_reference=body.reference
    return save(db,user,a,'appointment_status_changed')

@app.get('/api/v1/travel')
def travels(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,TravelRequest,user,200)]
@app.post('/api/v1/travel',status_code=201)
def travel(body:TravelIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_case(db,user,body.case_id)
    if body.service_type not in TRAVEL_TYPES:raise HTTPException(422,'Invalid service type')
    return save(db,user,TravelRequest(tenant_id=user.tenant_id,**body.model_dump()),'travel_service_requested')
@app.patch('/api/v1/travel/{id}/status')
def travel_status(id:str,body:StatusIn,db:Session=Depends(get_db),user:User=Depends(MANAGER)):
    t=require_owned(db,TravelRequest,id,user)
    # Legacy travel may record generic visa requests, but cannot certify approval.
    if t.service_type in ('visa', 'hotel', 'transport', 'interpreter') and body.status == 'confirmed' and body.reference:
        raise HTTPException(409, "Use dedicated coordination workflows for manual external-status reporting")
    if t.status!='requested' or body.status not in ('confirmed','cancelled'):raise HTTPException(409,'Invalid travel state')
    if body.status=='confirmed' and not body.reference:raise HTTPException(422,'External/human confirmation reference required')
    t.status=body.status;t.external_reference=body.reference
    return save(db,user,t,'travel_status_changed')

@app.get('/api/v1/conversations')
def conversations(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    # Keep legacy list compatible while hiding other operators' assignments.
    from .safety_rules import active_consent
    stmt=select(Conversation).where(Conversation.tenant_id==user.tenant_id)
    if user.role!='admin':
        stmt=stmt.where((Conversation.assigned_user_id==user.id)|
                        Conversation.assigned_user_id.is_(None))
    rows=db.scalars(stmt.order_by(Conversation.created_at.desc()).limit(200)).all()
    return [public(x) for x in rows
            if active_consent(db,user.tenant_id,x.patient_id,'communication')]
@app.post('/api/v1/conversations',status_code=201)
def conversation(body:ConversationIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_owned(db,Patient,body.patient_id,user)
    return save(db,user,Conversation(tenant_id=user.tenant_id,patient_id=body.patient_id,channel='webchat'),'conversation_created')
@app.get('/api/v1/conversations/{id}/messages')
def messages(id:str,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    from .human_inbox import require_thread,require_message_access
    c,_=require_thread(db,user,id)
    require_message_access(c,user)
    xs=db.scalars(select(Message).where(
        Message.tenant_id==user.tenant_id,Message.conversation_id==c.id
    ).order_by(Message.created_at.desc(),Message.id.desc()).limit(200)).all()
    return [public(x) for x in reversed(xs)]
@app.post('/api/v1/conversations/{id}/messages',status_code=201)
def message(id:str,body:MessageIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    from .human_inbox import reply,ReplyIn
    if body.language not in LANGUAGES:raise HTTPException(422,'Unsupported language')
    if len(body.body)>4000:raise HTTPException(422,'Reply exceeds secure inbox limit')
    return reply(id,ReplyIn(body=body.body,language=body.language),db,user)
@app.post('/api/v1/conversations/{id}/handoff')
def handoff(id:str,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    # Legacy API remains usable for pre-consent administrative handoff;
    # clinical and message content still require active consent.
    from .human_inbox import require_thread,ensure_thread,assign
    c,thread=require_thread(db,user,id,lock=True,consent=False)
    if user.role!='admin':
        need_consent(db,user,c.patient_id,'communication')
    if c.assigned_user_id not in (None,user.id):
        raise HTTPException(403,'Conversation belongs to a different operator')
    t=thread or ensure_thread(db,c)
    if t.status=='resolved':
        raise HTTPException(409,'Reopen conversation first')
    if c.assigned_user_id!=user.id:
        assign(db,c,t,user,user,'legacy_handoff_claimed')
    else:
        c.human_handoff=True
    # Preserve legacy audit event expected by existing operational audit logs.
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
                 event='conversation_handoff',entity_type='Conversation',entity_id=c.id))
    db.commit()
    return public(c)

@app.post('/api/v1/documents/upload-ticket')
def document_ticket(body:DocumentIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    c=require_case(db,user,body.case_id)
    if c.patient_id!=body.patient_id:raise HTTPException(422,'Case and patient do not match')
    need_consent(db,user,body.patient_id,'medical_documents')
    # Fail closed: no fake presigned URL, no misleading "uploaded" state.
    from .document_storage import local_enabled
    from .secure_media import s3_ready
    if not (s3_ready() or local_enabled()):
        raise HTTPException(503,'Private object storage and malware scanner must be configured before uploads are enabled')
    return {'status':'authenticated_upload_available','method':'multipart_post',
        'staff_endpoint':f'/api/v1/secure-documents/cases/{c.id}',
        'patient_endpoint':f'/api/v1/secure-documents/portal/cases/{c.id}',
        'requires_approved_private_patient_access':True,'presigned_public_url':None}

@app.get('/api/v1/tasks')
def tasks(db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    return [public(x) for x in listed(db,Task,user,200)]
@app.post('/api/v1/tasks',status_code=201)
def task(body:TaskIn,db:Session=Depends(get_db),user:User=Depends(MODERATOR)):
    require_case(db,user,body.case_id)
    return save(db,user,Task(tenant_id=user.tenant_id,**body.model_dump()),'task_created')

@app.get('/api/v1/audit')
def audits(limit:int=Query(100,ge=1,le=300),db:Session=Depends(get_db),user:User=Depends(roles('admin','auditor'))):
    return [public(x) for x in listed(db,Audit,user,limit)]

@app.get('/api/v1/integrations/status')
def integrations(user:User=Depends(MODERATOR)):
    return {'whatsapp':{'status':'inbound_configured_no_outbound' if __import__('app.whatsapp',fromlist=['enabled']).enabled() else 'blocked_pending_business_eligibility','live_connected':False},
            'telegram':{'status':'generic_onboarding_configured' if telegram_enabled() else 'disabled_or_not_configured','live_connected':False,'patient_data_ingestion':False},
            'ai':{'status':'enabled' if provider_available() else 'not_configured','live_connected':provider_available()},
            'file_uploads':{'status':'configured_pending_external_verification' if __import__('app.secure_media',fromlist=['s3_ready']).s3_ready() else 'not_configured','live_connected':False},
            'visa':{'status':'human_coordination_only','live_connected':False},
            'hotels':{'status':'human_coordination_only','live_connected':False},
            'medical_providers':{'status':'manual_verified_workflow','live_connected':False}}

# Enterprise domain routers (always enforce tenant and role boundaries)
from .enterprise_api import router as enterprise_router
app.include_router(enterprise_router)
from .patient_portal import router as patient_portal_router
app.include_router(patient_portal_router)
from .document_storage import router as document_storage_router
app.include_router(document_storage_router)

from .session_api import router as session_router
app.include_router(session_router)

from .communications import router as communications_router
app.include_router(communications_router)

from .portal_intake import router as portal_intake_router
app.include_router(portal_intake_router)

from .consent_links import router as consent_links_router
app.include_router(consent_links_router)

from .case_mission import router as case_mission_router
app.include_router(case_mission_router)

from .module_hub import router as module_hub_router
app.include_router(module_hub_router)

from .channel_gateway import router as channel_gateway_router
app.include_router(channel_gateway_router)

from .receptionist import router as receptionist_router
app.include_router(receptionist_router)

from .intake_coordination import router as intake_coordination_router
app.include_router(intake_coordination_router)

from .intake_clinical_review import router as intake_clinical_review_router
app.include_router(intake_clinical_review_router)

from .patient_crm import router as patient_crm_router
app.include_router(patient_crm_router)

from .admin_control import router as admin_control_router
app.include_router(admin_control_router)

from .human_inbox import router as human_inbox_router
app.include_router(human_inbox_router)

from .physician_management import router as physician_management_router
app.include_router(physician_management_router)

from .hospital_management import router as hospital_management_router
app.include_router(hospital_management_router)

from .provider_matching import router as provider_matching_router
app.include_router(provider_matching_router)

from .appointment_calendar import router as appointment_calendar_router
app.include_router(appointment_calendar_router)

from .quotation_versions import router as quotation_versions_router
app.include_router(quotation_versions_router)

from .visa_coordination import router as visa_coordination_router
app.include_router(visa_coordination_router)

from .accommodation import router as accommodation_router
app.include_router(accommodation_router)

from .travel_coordination import router as travel_coordination_router
app.include_router(travel_coordination_router)

from .international_agents import router as international_agents_router
app.include_router(international_agents_router)

from .portal_identity import router as portal_identity_router
app.include_router(portal_identity_router)

from .public_site import router as public_site_router
app.include_router(public_site_router)

from .cms_workflow import router as cms_workflow_router
app.include_router(cms_workflow_router)

from .tenant_isolation_status import router as tenant_isolation_router
app.include_router(tenant_isolation_router)

from .identity_governance import router as identity_governance_router
app.include_router(identity_governance_router)

from .privacy_governance import router as privacy_governance_router
app.include_router(privacy_governance_router)
