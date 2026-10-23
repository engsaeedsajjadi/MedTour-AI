"""Business-operations API: all records are tenant scoped, requests are not external confirmations."""
from __future__ import annotations
import json,re,secrets
from datetime import datetime,timezone
from typing import Any,Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Case,Patient,Quote,Consent,Audit,Task
from .enterprise_models import (Operation,OperationEvent,ServicePrice,QuoteItem,ContentPage,
    TenantSetting,KnowledgeArticle,AILog,PatientIntake,Notification,AgentProfile,
    LeadSource,MoneyEntry,CaseTimeline)
from .security import roles,current_user,password_hash
from .intake import LANGUAGES,PROMPTS,intake_response

router=APIRouter(prefix='/api/v1',tags=['enterprise'])
OPERATOR=roles('admin','operator')
ADMIN=roles('admin')
MANAGER=roles('admin')
CASE_SCOPED={'visa','hotel','transport','interpreter','home_visit','hospital_admission','diagnostics','followup','insurance','airport_pickup'}
GENERAL={'hotel_vendor','transport_vendor','interpreter_vendor','specialty','subscription_plan','agent_agreement'}
KINDS=CASE_SCOPED|GENERAL
MOVES={
    'requested':{'in_review','cancelled'},
    'in_review':{'awaiting_external','cancelled','rejected'},
    'awaiting_external':{'confirmed','rejected','cancelled'},
    'confirmed':{'completed','cancelled'},
    'completed':set(),'cancelled':set(),'rejected':set()
}
NO_AUTO_CONFIRM={'visa','hotel','hospital_admission','home_visit','diagnostics','airport_pickup','transport'}
ISO=re.compile(r'^[A-Z]{3}$')
SETTING_KEYS={'brand','business_contact','enabled_languages','notification_rules','consent_notice_version','locale','timezone','feature_flags','public_portal','service_categories'}

def owns(db:Session,model,pk:str,user:User):
    obj=db.scalar(select(model).where(model.id==pk,model.tenant_id==user.tenant_id))
    if obj is None:raise HTTPException(404,'Record not found')
    return obj

def check_case(db:Session,case_id:str,user:User):return owns(db,Case,case_id,user)

def log(db:Session,user:User,action:str,obj):
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event=action,entity_type=type(obj).__name__,entity_id=obj.id))

def write(db:Session,user:User,obj,action:str):
    db.add(obj);db.flush();log(db,user,action,obj);db.commit();db.refresh(obj);return obj

def operation_data(x:Operation):
    return dict(id=x.id,kind=x.kind,case_id=x.case_id,patient_id=x.patient_id,title=x.title,status=x.status,
        metadata=json.loads(x.metadata_json),assigned_to=x.assigned_to,confirmed_reference=x.confirmed_reference,
        approved_by=x.approved_by,created_at=x.created_at,updated_at=x.updated_at)

class OperationIn(BaseModel):
    kind:str
    case_id:str|None=None
    patient_id:str|None=None
    title:str=Field(min_length=3,max_length=250)
    metadata:dict[str,Any]=Field(default_factory=dict)
    assigned_to:str|None=None
    @field_validator('metadata')
    @classmethod
    def check_metadata(cls,v):
        if len(json.dumps(v,ensure_ascii=False))>6000:raise ValueError('Metadata too large')
        return v

@router.post('/operations',status_code=201)
def create_operation(body:OperationIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    if body.kind not in KINDS:raise HTTPException(422,'Unknown operation category')
    if body.kind in CASE_SCOPED and not body.case_id:raise HTTPException(422,'Case is required for this service')
    if body.case_id:
        c=check_case(db,body.case_id,user)
        if body.patient_id and body.patient_id!=c.patient_id:raise HTTPException(422,'Patient and case mismatch')
        body.patient_id=c.patient_id
    if body.patient_id:owns(db,Patient,body.patient_id,user)
    if body.assigned_to:owns(db,User,body.assigned_to,user)
    item=Operation(tenant_id=user.tenant_id,kind=body.kind,case_id=body.case_id,patient_id=body.patient_id,
                   title=body.title,metadata_json=json.dumps(body.metadata,ensure_ascii=False),assigned_to=body.assigned_to)
    return operation_data(write(db,user,item,'operation_created'))

@router.get('/operations')
def list_operations(kind:str|None=None,case_id:str|None=None,status:str|None=None,
    limit:int=Query(100,ge=1,le=300),db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    stmt=select(Operation).where(Operation.tenant_id==user.tenant_id)
    if kind:stmt=stmt.where(Operation.kind==kind)
    if case_id:stmt=stmt.where(Operation.case_id==case_id)
    if status:stmt=stmt.where(Operation.status==status)
    return [operation_data(o) for o in db.scalars(stmt.order_by(Operation.created_at.desc()).limit(limit)).all()]

class OperationChange(BaseModel):
    status:Literal['in_review','awaiting_external','confirmed','rejected','cancelled','completed']
    reference:str|None=Field(default=None,max_length=200)
    note:str=Field(default='',max_length=500)

@router.post('/operations/{pk}/transition')
def transition(pk:str,body:OperationChange,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    op=owns(db,Operation,pk,user)
    if body.status not in MOVES.get(op.status,set()):raise HTTPException(409,f'Invalid transition {op.status} to {body.status}')
    if body.status in ('confirmed','completed') and user.role!='admin':raise HTTPException(403,'Confirmation requires supervisor approval')
    if body.status=='confirmed' and not body.reference:raise HTTPException(422,'Independent provider/authority confirmation reference required')
    old=op.status;op.status=body.status
    if body.status=='confirmed':op.confirmed_reference=body.reference;op.approved_by=user.id
    db.add(OperationEvent(tenant_id=user.tenant_id,operation_id=op.id,actor_id=user.id,
           old_status=old,new_status=body.status,note=body.note))
    return operation_data(write(db,user,op,'operation_state_changed'))

@router.get('/operations/{pk}/history')
def operation_history(pk:str,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    owns(db,Operation,pk,user)
    rows=db.scalars(select(OperationEvent).where(OperationEvent.tenant_id==user.tenant_id,
           OperationEvent.operation_id==pk).order_by(OperationEvent.created_at)).all()
    return [{'previous':x.old_status,'current':x.new_status,'note':x.note,'at':x.created_at,'actor_id':x.actor_id} for x in rows]

class AgentIn(BaseModel):
    name:str=Field(min_length=2,max_length=200)
    country:str=Field(min_length=2,max_length=100)

@router.post('/agents',status_code=201)
def create_agent(body:AgentIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    a=AgentProfile(tenant_id=user.tenant_id,name=body.name,country=body.country,referral_code=secrets.token_urlsafe(12))
    write(db,user,a,'agent_created');return {'id':a.id,'name':a.name,'country':a.country,'referral_code':a.referral_code,'active':a.active}

@router.get('/agents')
def agents(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    return [{'id':a.id,'name':a.name,'country':a.country,'referral_code':a.referral_code,'active':a.active} for a in db.scalars(
        select(AgentProfile).where(AgentProfile.tenant_id==user.tenant_id).order_by(AgentProfile.created_at.desc())).all()]

class LeadIn(BaseModel):
    patient_id:str
    agent_id:str|None=None
    source:str=Field(default='direct',max_length=80)
    campaign:str=Field(default='',max_length=120)

@router.post('/lead-sources',status_code=201)
def lead(body:LeadIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    owns(db,Patient,body.patient_id,user)
    if body.agent_id:owns(db,AgentProfile,body.agent_id,user)
    x=LeadSource(tenant_id=user.tenant_id,**body.model_dump());write(db,user,x,'lead_source_attributed')
    return {'id':x.id,'source':x.source,'agent_id':x.agent_id,'patient_id':x.patient_id}

@router.get('/lead-sources')
def lead_sources(db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    rows=db.scalars(select(LeadSource).where(LeadSource.tenant_id==user.tenant_id).limit(200)).all()
    return [{'id':x.id,'source':x.source,'agent_id':x.agent_id,'patient_id':x.patient_id,'campaign':x.campaign} for x in rows]

class ContentIn(BaseModel):
    slug:str=Field(min_length=2,max_length=150,pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    locale:str
    title:str=Field(min_length=2,max_length=250)
    body:str=Field(min_length=1,max_length=30000)

@router.post('/cms/pages',status_code=201)
def cms_add(body:ContentIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if body.locale not in LANGUAGES:raise HTTPException(422,'Unsupported locale')
    try:
        x=ContentPage(tenant_id=user.tenant_id,**body.model_dump());write(db,user,x,'content_drafted')
        return {'id':x.id,'slug':x.slug,'locale':x.locale,'status':x.status}
    except IntegrityError:
        db.rollback();raise HTTPException(409,'A page for this slug and locale already exists')

@router.get('/cms/pages')
def cms_list(db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    rows=db.scalars(select(ContentPage).where(ContentPage.tenant_id==user.tenant_id).limit(200)).all()
    return [{'id':x.id,'slug':x.slug,'locale':x.locale,'title':x.title,'status':x.status} for x in rows]

@router.patch('/cms/pages/{pk}/publish')
def cms_publish(pk:str,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    x=owns(db,ContentPage,pk,user);x.status='published';x.approved_by=user.id
    write(db,user,x,'content_published');return {'id':x.id,'status':x.status}

@router.get('/public/{tenant_slug}/pages/{locale}/{slug}')
def public_page(tenant_slug:str,locale:str,slug:str,db:Session=Depends(get_db)):
    from .models import Tenant
    tenant=db.scalar(select(Tenant).where(Tenant.slug==tenant_slug))
    if not tenant:raise HTTPException(404,'Page not found')
    x=db.scalar(select(ContentPage).where(ContentPage.tenant_id==tenant.id,ContentPage.locale==locale,
           ContentPage.slug==slug,ContentPage.status=='published'))
    if not x:raise HTTPException(404,'Page not found')
    return {'title':x.title,'body':x.body,'locale':x.locale,'slug':x.slug}

class KnowledgeIn(BaseModel):
    locale:str
    title:str=Field(min_length=3,max_length=240)
    body:str=Field(min_length=10,max_length=20000)

@router.post('/knowledge',status_code=201)
def knowledge_create(body:KnowledgeIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    if body.locale not in LANGUAGES:raise HTTPException(422,'Unsupported locale')
    x=KnowledgeArticle(tenant_id=user.tenant_id,**body.model_dump());write(db,user,x,'knowledge_drafted')
    return {'id':x.id,'approved':False}

@router.patch('/knowledge/{pk}/approve')
def knowledge_approve(pk:str,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    x=owns(db,KnowledgeArticle,pk,user);x.approved=True;x.approved_by=user.id
    write(db,user,x,'knowledge_approved');return {'id':x.id,'approved':True}

@router.get('/knowledge')
def knowledge_list(db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    rows=db.scalars(select(KnowledgeArticle).where(KnowledgeArticle.tenant_id==user.tenant_id).limit(200)).all()
    return [{'id':x.id,'locale':x.locale,'title':x.title,'approved':x.approved} for x in rows]

class PriceIn(BaseModel):
    service_code:str=Field(min_length=2,max_length=90)
    label:str=Field(min_length=3,max_length=200)
    currency:str=Field(min_length=3,max_length=3)
    amount_minor:int=Field(ge=0,le=10**15)
    source:str=Field(min_length=5,max_length=180)
    valid_until:datetime

@router.post('/prices',status_code=201)
def price_create(body:PriceIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if not ISO.fullmatch(body.currency.upper()):raise HTTPException(422,'Invalid currency')
    if body.valid_until.tzinfo is None:raise HTTPException(422,'Timezone-aware valid_until required')
    if body.valid_until<=datetime.now(timezone.utc):raise HTTPException(422,'Price already expired')
    x=ServicePrice(tenant_id=user.tenant_id,**(body.model_dump()|{'currency':body.currency.upper()}),verified_by=user.id)
    write(db,user,x,'service_price_verified')
    return {'id':x.id,'service_code':x.service_code,'currency':x.currency,'amount_minor':x.amount_minor,'valid_until':x.valid_until}

@router.get('/prices')
def prices(db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    rows=db.scalars(select(ServicePrice).where(ServicePrice.tenant_id==user.tenant_id,ServicePrice.active==True).limit(200)).all()
    return [{'id':x.id,'label':x.label,'service_code':x.service_code,'currency':x.currency,
             'amount_minor':x.amount_minor,'source':x.source,'valid_until':x.valid_until} for x in rows]

class ItemIn(BaseModel):
    label:str=Field(min_length=3,max_length=200)
    units:int=Field(ge=1,le=100000)
    unit_amount_minor:int=Field(ge=0,le=10**14)
    provenance:str=Field(min_length=4,max_length=300)

@router.post('/quotes/{pk}/items',status_code=201)
def add_quote_item(pk:str,body:ItemIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    q=owns(db,Quote,pk,user)
    if q.status!='draft':raise HTTPException(409,'Cannot change approved quotation')
    row=QuoteItem(tenant_id=user.tenant_id,quote_id=q.id,**body.model_dump())
    db.add(row);db.flush()
    line_total=body.units*body.unit_amount_minor
    if q.amount_minor+line_total>10**15:raise HTTPException(422,'Quote total exceeds limit')
    q.amount_minor+=line_total
    log(db,user,'quote_line_added',row);db.commit()
    return {'id':row.id,'quote_id':pk,'line_amount_minor':line_total,'quote_total_minor':q.amount_minor}

@router.get('/quotes/{pk}/items')
def quote_items(pk:str,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    owns(db,Quote,pk,user)
    rows=db.scalars(select(QuoteItem).where(QuoteItem.tenant_id==user.tenant_id,QuoteItem.quote_id==pk)).all()
    return [{'id':x.id,'label':x.label,'units':x.units,'unit_amount_minor':x.unit_amount_minor,'provenance':x.provenance} for x in rows]

class MoneyIn(BaseModel):
    case_id:str
    entry_type:Literal['payment_received','refund_issued','service_expense','agency_fee']
    currency:str=Field(min_length=3,max_length=3)
    amount_minor:int=Field(gt=0,le=10**15)
    source_reference:str=Field(min_length=3,max_length=200)

@router.post('/finance/entries',status_code=201)
def finance_create(body:MoneyIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    check_case(db,body.case_id,user)
    if not ISO.fullmatch(body.currency.upper()):raise HTTPException(422,'Invalid currency')
    x=MoneyEntry(tenant_id=user.tenant_id,**(body.model_dump()|{'currency':body.currency.upper()}),verified_by=user.id)
    try:
        write(db,user,x,'verified_manual_money_entry')
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Duplicate financial reference')
    return {'id':x.id,'entry_type':x.entry_type,'amount_minor':x.amount_minor,'currency':x.currency,'source_reference':x.source_reference,'verified':True}

@router.get('/finance/entries')
def finance_list(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    xs=db.scalars(select(MoneyEntry).where(MoneyEntry.tenant_id==user.tenant_id).limit(200)).all()
    return [{'id':x.id,'case_id':x.case_id,'entry_type':x.entry_type,'amount_minor':x.amount_minor,
             'currency':x.currency,'source_reference':x.source_reference} for x in xs]

class ConfigIn(BaseModel):
    value:dict[str,Any]

@router.get('/settings')
def settings(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    rows=db.scalars(select(TenantSetting).where(TenantSetting.tenant_id==user.tenant_id)).all()
    return {x.key:json.loads(x.value_json) for x in rows if x.key in SETTING_KEYS}

@router.put('/settings/{key}')
def setting_write(key:str,body:ConfigIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if key not in SETTING_KEYS:raise HTTPException(422,'Setting key is not allowed')
    serial=json.dumps(body.value,ensure_ascii=False)
    if len(serial)>8000:raise HTTPException(413,'Setting too large')
    x=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==user.tenant_id,TenantSetting.key==key))
    if x:x.value_json=serial
    else:x=TenantSetting(tenant_id=user.tenant_id,key=key,value_json=serial)
    write(db,user,x,'tenant_setting_updated')
    return {'key':key,'value':body.value}

@router.get('/reports/operations')
def reports(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    query=db.execute(select(Operation.kind,Operation.status,func.count()).where(Operation.tenant_id==user.tenant_id).group_by(Operation.kind,Operation.status)).all()
    return {'operations':[{'kind':k,'status':s,'count':count} for k,s,count in query],
        'verified_payments':db.scalar(select(func.count()).select_from(MoneyEntry).where(MoneyEntry.tenant_id==user.tenant_id,MoneyEntry.entry_type=='payment_received')),
        'agents':db.scalar(select(func.count()).select_from(AgentProfile).where(AgentProfile.tenant_id==user.tenant_id)),
        'manual_coordination_only':True}

class StaffIn(BaseModel):
    email:str=Field(min_length=6,max_length=250)
    password:str=Field(min_length=12,max_length=250)
    role:Literal['operator','auditor','admin','physician']

@router.post('/staff',status_code=201)
def staff_create(body:StaffIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    email=body.email.strip().lower()
    if '@' not in email:raise HTTPException(422,'Invalid email')
    staff=User(tenant_id=user.tenant_id,email=email,password_hash=password_hash(body.password),role=body.role)
    try:write(db,user,staff,'staff_created')
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Staff email already registered')
    return {'id':staff.id,'email':staff.email,'role':staff.role}

@router.get('/staff')
def staff_list(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    xs=db.scalars(select(User).where(User.tenant_id==user.tenant_id)).all()
    return [{'id':x.id,'email':x.email,'role':x.role,'active':x.active} for x in xs]

# Staged structured intake remains human-managed; no autonomous medical diagnosis.
from .intake import QUESTION_KEYS,next_question
class IntakeStart(BaseModel):
    case_id:str
    language:str='en'

@router.post('/intake/sessions',status_code=201)
def intake_start(body:IntakeStart,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    from .intake_coordination import prepare_intake_start
    from .safety_rules import active_consent
    c=check_case(db,body.case_id,user)
    if not active_consent(db,user.tenant_id,c.patient_id,'intake'):
        raise HTTPException(409,'Active intake consent required')
    row,created=prepare_intake_start(db,c,body.language)
    if created:log(db,user,'intake_session_started',row)
    db.commit()
    return {'id':row.id,'stage':row.stage,
            'question_key':QUESTION_KEYS[row.stage] if row.stage<len(QUESTION_KEYS) else None,
            'prompt':next_question(row.language,row.stage) if row.stage<len(QUESTION_KEYS) else None,
            'reused':not created}

class AnswerIn(BaseModel):
    answer:str=Field(min_length=1,max_length=3000)

@router.post('/intake/sessions/{pk}/answer')
def intake_answer(pk:str,body:AnswerIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    from .safety_rules import active_consent
    x=db.scalar(select(PatientIntake).where(
        PatientIntake.id==pk,PatientIntake.tenant_id==user.tenant_id
    ).with_for_update())
    if not x:raise HTTPException(404,'Intake not found')
    case=check_case(db,x.case_id,user)
    if not active_consent(db,user.tenant_id,case.patient_id,'intake'):
        raise HTTPException(409,'Active intake consent required')
    if x.status!='in_progress':raise HTTPException(409,'Intake session finished')
    if not body.answer.strip():raise HTTPException(422,'Nonblank intake answer required')
    if x.stage>=len(QUESTION_KEYS):raise HTTPException(409,'Intake already complete')
    safety=intake_response(x.language,body.answer)
    if safety['emergency_keyword_detected']:
        x.status='requires_urgent_human_review'
        write(db,user,x,'intake_emergency_warning')
        return {'status':x.status,'warning':safety['message'],'emergency_keyword_detected':True}
    answers=json.loads(x.answers_json)
    answers[QUESTION_KEYS[x.stage]]=body.answer
    x.answers_json=json.dumps(answers,ensure_ascii=False)
    x.stage+=1
    if x.stage==len(QUESTION_KEYS):x.status='awaiting_clinician_review'
    write(db,user,x,'intake_answer_recorded')
    return {'id':x.id,'status':x.status,'stage':x.stage,'next_question_key':QUESTION_KEYS[x.stage] if x.status=='in_progress' else None,'next_prompt':next_question(x.language,x.stage) if x.status=='in_progress' else None,'human_review_required':True}

@router.get('/intake/sessions/{pk}')
def intake_read(pk:str,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    from .safety_rules import active_consent
    x=owns(db,PatientIntake,pk,user)
    case=check_case(db,x.case_id,user)
    if not active_consent(db,user.tenant_id,case.patient_id,'intake'):
        raise HTTPException(409,'Active intake consent required')
    return {'id':x.id,'case_id':x.case_id,'language':x.language,'stage':x.stage,
            'status':x.status,'answers':json.loads(x.answers_json),
            'clinical_validation':'not_performed'}

@router.get('/notifications')
def notifications(db:Session=Depends(get_db),user:User=Depends(current_user)):
    xs=db.scalars(select(Notification).where(Notification.tenant_id==user.tenant_id,Notification.recipient_id==user.id).limit(100)).all()
    return [{'id':x.id,'title':x.title,'body':x.body,'read':x.read_at is not None} for x in xs]

@router.get('/ai/usage')
def ai_usage(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    xs=db.execute(select(AILog.provider,AILog.outcome,func.count(),func.sum(AILog.tokens)).where(AILog.tenant_id==user.tenant_id).group_by(AILog.provider,AILog.outcome)).all()
    return [{'provider':a,'outcome':b,'calls':c,'tokens':d or 0} for a,b,c,d in xs]

class ProviderFindIn(BaseModel):
    case_id:str
    preferred_city:str|None=Field(default=None,max_length=100)

@router.post('/provider-options')
def provider_options(body:ProviderFindIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    from .models import Physician,Hospital
    c=check_case(db,body.case_id,user)
    # Administrative directory search only: no autonomous clinical suitability determination.
    physicians=db.scalars(select(Physician).where(Physician.tenant_id==user.tenant_id,Physician.credential_status=='verified')).all()
    matches=[p for p in physicians if p.specialty.casefold()==c.specialty.casefold()]
    if body.preferred_city:matches=[p for p in matches if p.city.casefold()==body.preferred_city.casefold()]
    return {'status':'requires_human_clinical_review','matched_specialty':c.specialty,
      'results':[{'id':p.id,'name':p.full_name,'specialty':p.specialty,'city':p.city,
                  'matching_reason':'Administratively marked directory record and matching specialty text; independent license NOT verified'} for p in matches],
      'disclaimer':'Not a medical recommendation or treatment decision. Directory verified flag alone is NOT independent licensure verification.',
      'independent_licensure_verified':False,
      'clinic_appointment_booked':False}

@router.get('/knowledge/search')
def knowledge_search(q:str=Query(min_length=3,max_length=120),locale:str='en',db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    if locale not in LANGUAGES:raise HTTPException(422,'Unsupported locale')
    articles=db.scalars(select(KnowledgeArticle).where(KnowledgeArticle.tenant_id==user.tenant_id,
                   KnowledgeArticle.locale==locale,KnowledgeArticle.approved==True).limit(500)).all()
    words=set(q.casefold().split())
    ranked=sorted(((sum(1 for w in words if w in (a.title+' '+a.body).casefold()),a) for a in articles),key=lambda x:x[0],reverse=True)
    return [{'id':a.id,'title':a.title,'excerpt':a.body[:400],'approved':True,
             'matching_terms':score} for score,a in ranked if score>0][:10]

class TranslateIn(BaseModel):
    patient_id:str
    target_language:str
    source_language:str
    text:str=Field(min_length=1,max_length=2400)

@router.post('/ai/translate-draft')
def translate_draft(body:TranslateIn,db:Session=Depends(get_db),user:User=Depends(OPERATOR)):
    from .ai import translate
    owns(db,Patient,body.patient_id,user)
    if body.target_language not in LANGUAGES or body.source_language not in LANGUAGES:raise HTTPException(422,'Unsupported language')
    c=db.scalar(select(Consent).where(Consent.tenant_id==user.tenant_id,Consent.patient_id==body.patient_id,
       Consent.purpose=='ai_processing').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    if not c or not c.accepted:raise HTTPException(409,'AI processing consent required')
    answer=translate(body.text,body.source_language,body.target_language)
    return {'translation_draft':answer,'human_review_required':True,
      'warning':'A qualified human must verify translation of clinically important information before delivery.'}
