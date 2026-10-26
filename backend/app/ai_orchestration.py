"""Section 24: audited, opt-in, bounded multi-agent administrative orchestrator.

NO patient/case/conversation/document fields in the request. An agent can
read IDs of tenant-approved knowledge items only; there is no write-capable
tool, external send action, clinical decision or provider credential access.
Model calls receive static template text only, never private records.
"""
from __future__ import annotations

import hashlib,json,os,re
from datetime import datetime,timedelta,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import User,Audit,Tenant
from .enterprise_models import AIAgentPolicy,AIOrchestrationRun,AIOrchestrationEvent,KnowledgeArticle
from .security import roles
from .receptionist import RESPONSES
from .ai import provider_available,draft as provider_draft

router=APIRouter(prefix="/ai-orchestration",tags=["administrative AI orchestration"])
ADMIN=roles("admin")
STAFF=roles("admin","operator")
LOCALES=("fa","ar","en","ps","prs")
AGENTS={
 "administrative_receptionist":{
    "workflows":("general_information","document_safety","human_handoff"),
    "tool_permissions":("read_approved_knowledge_metadata",)},
 "travel_coordinator":{
    "workflows":("travel_process","appointment_process"),
    "tool_permissions":("read_approved_knowledge_metadata",)},
 "knowledge_assistant":{
    "workflows":("general_information","knowledge_discovery"),
    "tool_permissions":("read_approved_knowledge_metadata",)},
}
# Each workflow maps to pre-vetted generic receptionist templates; no PHI.
WORKFLOW_TEMPLATES={
 "general_information":"general",
 "document_safety":"documents",
 "human_handoff":"human",
 "travel_process":"visa",
 "appointment_process":"appointment",
 "knowledge_discovery":"general",
}
STATIC_PROVIDER_TASKS={
 "general_information":"Give a short generic description of the nonclinical administrative medical travel inquiry process. No patient case details.",
 "document_safety":"Explain that medical documents require explicit consent and the separately approved secure portal. Never request or repeat documents.",
 "human_handoff":"Explain how a staff member can review a general administrative inquiry. No emergency or treatment guidance.",
 "travel_process":"Explain that visa, transport and lodging services require independently verified human review, not a guaranteed booking.",
 "appointment_process":"Explain that appointment requests need external clinic confirmation and a responsible human coordinator.",
 "knowledge_discovery":"Explain that generic published administrative knowledge requires human verification and cannot answer clinical questions.",
}
EXTERNAL_BLOCKS=(
 "diagnosis","diagnose","prescription","prescribe","100%","guaranteed cure",
 "guaranteed treatment","medical diagnosis","clinical recommendation",
 "تشخیص قطعی","درمان قطعی","نسخه دارویی","تضمین درمان",
 "تشخيص نهائي","علاج مضمون","وصفة طبية",
)
# Defense in depth. The provider response is *not* relied upon as a medical
# safety classifier and must never be delivered without human review.
PRIVATE_PATTERNS=(
 re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b"),
 re.compile(r"\b\+?\d[\d\s-]{9,}\d\b"),
)
MAX_PER_DAY=100
MAX_TEXT=1200

def allowed_env():
    if os.getenv("APP_ENV","development").lower() not in ("development","test"):
        raise HTTPException(503,"Real-patient AI orchestration not approved; development-only")

def fingerprint(agent,workflow,locale,mode):
    return hashlib.sha256(json.dumps([agent,workflow,locale,mode],
        separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def guard_outcome(text):
    if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT:
        return False
    raw=text.lower()
    return not any(term in raw for term in EXTERNAL_BLOCKS) and not any(
        pattern.search(text) for pattern in PRIVATE_PATTERNS)

def is_policy_enabled(db,tenant,agent_key):
    p=db.scalar(select(AIAgentPolicy).where(AIAgentPolicy.tenant_id==tenant,
        AIAgentPolicy.agent_key==agent_key))
    if not p or not p.enabled:raise HTTPException(409,"Agent is disabled for tenant")
    return p

def owned(db,user,model,id,lock=False):
    q=select(model).where(model.tenant_id==user.tenant_id,model.id==id)
    item=db.scalar(q.with_for_update() if lock else q)
    if not item:raise HTTPException(404,"Agent run not found")
    return item

def event(db,user,run,action,detail):
    db.add(AIOrchestrationEvent(tenant_id=user.tenant_id,run_id=run.id,
        actor_id=user.id,action=action,detail_code=detail))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event=action,
        entity_type="AIOrchestrationRun",entity_id=run.id))

def render(run):
    return {
        "id":run.id,"request_key":run.request_key,
        "agent_key":run.agent_key,"workflow":run.workflow,"locale":run.locale,
        "status":run.status,"mode":run.mode,
        "display_text":run.result_text,"knowledge_reference_ids":json.loads(run.knowledge_ids_json),
        "authored_by":run.authored_by,"reviewer_id":run.reviewer_id,
        "created_at":run.created_at,"sent":False,"clinical_decision":False,
        "patient_data_processed":False,"review_required":run.status=="pending_human_review",
        "provider_verified":run.mode=="approved_provider" and provider_available(),
    }

def knowledge_metadata(db,tenant,locale,workflow):
    # Lexical discovery ONLY over tenant-approved titles. Content/body never
    # sent to the external model, used as clinical context or returned here.
    keywords=set(workflow.replace("_"," ").split())
    approved=db.scalars(select(KnowledgeArticle).where(
        KnowledgeArticle.tenant_id==tenant,KnowledgeArticle.locale==locale,
        KnowledgeArticle.approved.is_(True)).order_by(KnowledgeArticle.created_at.desc()).limit(80)).all()
    ranked=sorted(approved,key=lambda x:sum(k in x.title.lower() for k in keywords),reverse=True)
    return [x.id for x in ranked[:3] if x.title and
            (workflow=="knowledge_discovery" or any(k in x.title.lower() for k in keywords))]

@router.get("/catalog")
def catalog(db:Session=Depends(get_db),user:User=Depends(STAFF)):
    configured={p.agent_key:p for p in db.scalars(select(AIAgentPolicy).where(
        AIAgentPolicy.tenant_id==user.tenant_id)).all()}
    return {"agents":[{"agent_key":key,"allowed_workflows":list(v["workflows"]),
             "tool_permissions":list(v["tool_permissions"]),
             "enabled":bool(configured.get(key) and configured[key].enabled),
             "provider_mode":configured[key].provider_mode if key in configured else "deterministic_demo",
             "daily_run_limit":configured[key].daily_run_limit if key in configured else 20
            } for key,v in AGENTS.items()],
            "real_ai_provider_ready":provider_available(),
            "approved_knowledge_retrieval":"IDs only, not validated RAG",
            "external_tools_enabled":False,"auto_send_enabled":False,
            "medical_decision_enabled":False,"phi_processing_enabled":False,
            "external_provider_configured_independently":False}

class AgentConfig(BaseModel):
    model_config=ConfigDict(extra="forbid")
    enabled:bool
    provider_mode:Literal["deterministic_demo","approved_provider"]
    daily_run_limit:int=Field(ge=1,le=MAX_PER_DAY)

@router.put("/agents/{agent_key}")
def configure(agent_key:str,body:AgentConfig,db:Session=Depends(get_db),
              user:User=Depends(ADMIN)):
    if agent_key not in AGENTS:raise HTTPException(404,"Agent unavailable")
    # Serialize policy edits with run creation for this tenant.
    db.scalar(select(Tenant.id).where(Tenant.id==user.tenant_id).with_for_update())
    if body.enabled:
        allowed_env()
        if body.provider_mode=="approved_provider" and not provider_available():
            raise HTTPException(503,"Approved provider host and credentials required")
    p=db.scalar(select(AIAgentPolicy).where(AIAgentPolicy.tenant_id==user.tenant_id,
        AIAgentPolicy.agent_key==agent_key).with_for_update())
    if not p:
        p=AIAgentPolicy(tenant_id=user.tenant_id,agent_key=agent_key,
            updated_by=user.id,enabled=body.enabled,
            provider_mode=body.provider_mode,daily_run_limit=body.daily_run_limit)
        db.add(p)
    else:
        p.enabled=body.enabled;p.provider_mode=body.provider_mode
        p.daily_run_limit=body.daily_run_limit;p.updated_by=user.id
    db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="ai_agent_policy_changed",
        entity_type="AIAgentPolicy",entity_id=p.id))
    db.commit()
    return {"agent_key":agent_key,"enabled":p.enabled,
        "provider_mode":p.provider_mode,"daily_run_limit":p.daily_run_limit,
        "human_review_mandatory":True,"external_actions_enabled":False}

class RunIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=8,max_length=100,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")
    agent_key:Literal["administrative_receptionist","travel_coordinator","knowledge_assistant"]
    workflow:Literal["general_information","document_safety","human_handoff",
                     "travel_process","appointment_process","knowledge_discovery"]
    locale:Literal["fa","ar","en","ps","prs"]

@router.post("/runs",status_code=201)
def run(body:RunIn,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    allowed_env()
    # Requests intentionally exclude free-text, patient_id, case_id, tool
    # arguments, arbitrary URLs or uploads. No egress to patient record tools.
    if body.workflow not in AGENTS[body.agent_key]["workflows"]:
        raise HTTPException(422,"Workflow unavailable for this agent")
    # PostgreSQL tenant row lock makes daily-budget checks and request
    # idempotency atomic across workers and across enabled agents.
    db.scalar(select(Tenant.id).where(Tenant.id==user.tenant_id).with_for_update())
    policy=is_policy_enabled(db,user.tenant_id,body.agent_key)
    content_hash=fingerprint(body.agent_key,body.workflow,body.locale,policy.provider_mode)
    previous=db.scalar(select(AIOrchestrationRun).where(
        AIOrchestrationRun.tenant_id==user.tenant_id,
        AIOrchestrationRun.request_key==body.request_key))
    if previous:
        if previous.input_hash!=content_hash:
            raise HTTPException(409,"Idempotency-key conflict")
        return {**render(previous),"deduplicated":True}
    start=datetime.now(timezone.utc)-timedelta(days=1)
    total=db.scalar(select(func.count()).select_from(AIOrchestrationRun).where(
        AIOrchestrationRun.tenant_id==user.tenant_id,
        AIOrchestrationRun.created_at>=start))
    if total>=policy.daily_run_limit:raise HTTPException(429,"Tenant daily AI run budget exceeded")
    refs=knowledge_metadata(db,user.tenant_id,body.locale,body.workflow)
    # A deterministic, carefully constrained administrative fallback is NOT AI.
    fallback=RESPONSES[body.locale][WORKFLOW_TEMPLATES[body.workflow]][:MAX_TEXT]
    status="pending_human_review";out=fallback
    mode=policy.provider_mode
    if mode=="approved_provider":
        if not provider_available():
            raise HTTPException(503,"Approved AI provider currently unavailable")
        # This request is STATIC and non-identifying. Never send knowledge
        # contents, patient messages, PHI, or user-provided instruction text.
        result=provider_draft(STATIC_PROVIDER_TASKS[body.workflow],body.locale)
        proposed=result.get("message","")
        if not guard_outcome(proposed):
            out=fallback;status="blocked_quality_gate"
        else:out=proposed
    row=AIOrchestrationRun(tenant_id=user.tenant_id,
        request_key=body.request_key,input_hash=content_hash,
        agent_key=body.agent_key,workflow=body.workflow,locale=body.locale,
        status=status,mode=mode,result_text=out,
        knowledge_ids_json=json.dumps(refs),authored_by=user.id)
    db.add(row);db.flush()
    event(db,user,row,"ai_orchestration_draft_created",status)
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,"Duplicate AI request key")
    return {**render(row),"deduplicated":False}

@router.get("/runs")
def runs(db:Session=Depends(get_db),user:User=Depends(STAFF),
         limit:int=Query(50,ge=1,le=100)):
    xs=db.scalars(select(AIOrchestrationRun).where(
        AIOrchestrationRun.tenant_id==user.tenant_id).order_by(
        AIOrchestrationRun.created_at.desc()).limit(limit)).all()
    return {"items":[render(x) for x in xs],
        "all_outputs_human_reviewed_before_any_use":False,
        "external_delivery_capability":False}

@router.get("/runs/{run_id}")
def run_detail(run_id:str,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    return render(owned(db,user,AIOrchestrationRun,run_id))

class DecisionIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["approve_internal","reject"]
    evidence_reference:str=Field(min_length=6,max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$")

@router.post("/runs/{run_id}/review")
def review(run_id:str,body:DecisionIn,db:Session=Depends(get_db),
           user:User=Depends(ADMIN)):
    row=owned(db,user,AIOrchestrationRun,run_id,True)
    if row.status not in ("pending_human_review","blocked_quality_gate"):
        raise HTTPException(409,"Review already finalized")
    if user.id==row.authored_by:
        raise HTTPException(409,"Reviewer must differ from original operator")
    if body.decision=="approve_internal":
        if row.status=="blocked_quality_gate":
            raise HTTPException(409,"Safety-failed model output cannot be approved")
        is_policy_enabled(db,user.tenant_id,row.agent_key)
        row.status="approved_for_internal_reference"
    else:
        row.status="rejected"
    row.reviewer_id=user.id;row.decision_reference=body.evidence_reference
    event(db,user,row,"ai_orchestration_human_reviewed",row.status)
    db.commit()
    return {**render(row),"external_message_sent":False,
        "clinical_use_authorized":False,"financial_action_taken":False}

@router.get("/runs/{run_id}/events")
def history(run_id:str,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    row=owned(db,user,AIOrchestrationRun,run_id)
    events=db.scalars(select(AIOrchestrationEvent).where(
        AIOrchestrationEvent.tenant_id==user.tenant_id,
        AIOrchestrationEvent.run_id==row.id).order_by(
        AIOrchestrationEvent.created_at.desc()).limit(100)).all()
    return {"items":[{"id":e.id,"actor_id":e.actor_id,
        "action":e.action,"detail_code":e.detail_code,
        "created_at":e.created_at} for e in events]}
