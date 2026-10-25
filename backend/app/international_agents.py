"""Section 20 international agents: strictly nonclinical, privacy-minimal alpha portal.

Admin review of a draft is NOT contract enforceability, lawful referral compensation,
a KYC check, or a financial payout approval. No production patient information.
"""
from __future__ import annotations

import re
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,EmailStr,Field
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import User,Patient,Audit
from .enterprise_models import (AgentProfile,AgentAgreement,AgentIdentity,
    AgentReferralIntent,AgentCommercialDraft,AgentGovernanceEvent,LeadSource,
    RefreshSession)
from .security import roles,password_hash
from .safety_rules import active_consent

router=APIRouter(prefix="/api/v1/agent-network",tags=["international agents governance"])
admin=roles("admin")
agent_role=roles("agent")
KEY=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$"
REF=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
COUNTRY=r"^[A-Z]{2}$"
CURRENCY=r"^[A-Z]{3}$"
ACTIVE_AGREEMENT="administratively_reviewed"

def own(db,user,model,id,lock=False):
    stmt=select(model).where(model.tenant_id==user.tenant_id,model.id==id)
    item=db.scalar(stmt.with_for_update() if lock else stmt)
    if item is None:raise HTTPException(404,"Record not found")
    return item

def agent_guard(db,user,id,lock=False):
    a=own(db,user,AgentProfile,id,lock)
    if not a.active:raise HTTPException(409,"Agent disabled")
    return a

def contract_guard(db,user,agent_id,lock=False):
    q=select(AgentAgreement).where(
        AgentAgreement.tenant_id==user.tenant_id,
        AgentAgreement.agent_id==agent_id,
        AgentAgreement.status==ACTIVE_AGREEMENT).order_by(AgentAgreement.created_at.desc())
    agreement=db.scalar((q.with_for_update() if lock else q).limit(1))
    if not agreement:raise HTTPException(409,"Administratively reviewed agreement required")
    return agreement

def portal_identity(db,user):
    p=db.scalar(select(AgentIdentity).where(
        AgentIdentity.tenant_id==user.tenant_id,AgentIdentity.user_id==user.id))
    if not p:raise HTTPException(403,"Agent portal account not provisioned")
    a=agent_guard(db,user,p.agent_id)
    return a,p

def log(db,user,row,event,agent_id):
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event=event,entity_type=type(row).__name__,entity_id=row.id))
    db.add(AgentGovernanceEvent(tenant_id=user.tenant_id,actor_id=user.id,
        agent_id=agent_id,entity_kind=type(row).__name__,entity_id=row.id,
        action=event,reference="metadata_only"))

def contract_view(x):
    return dict(id=x.id,agent_id=x.agent_id,jurisdiction=x.jurisdiction,
        contract_key=x.contract_key,scope=x.scope,currency=x.currency,
        max_budget_minor=x.max_budget_minor,status=x.status,
        document_reference=x.document_reference,
        government_or_legal_approval_verified=False,
        binding_contract_verified=False,compensation_payable=False)

def intent_view(x):
    # No patient_id, contact, case_id, clinical or financial information for agents.
    return dict(id=x.id,request_key=x.request_key,channel=x.channel,
        campaign_code=x.campaign_code,status=x.status,created_at=x.created_at,
        patient_information_shared=False,medical_data_shared=False)

def commercial_view(x):
    return dict(id=x.id,agent_id=x.agent_id,agreement_id=x.agreement_id,
        draft_key=x.draft_key,activity_reference=x.activity_reference,
        amount_minor=x.amount_minor,status=x.status,
        payout_authorized=False,external_compliance_cleared=False)

class ContractIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    contract_key:str=Field(min_length=8,max_length=100,pattern=KEY)
    jurisdiction:str=Field(pattern=COUNTRY)
    currency:str=Field(pattern=CURRENCY)
    scope:Literal["nonclinical_marketing","nonclinical_logistics"]="nonclinical_marketing"
    max_budget_minor:int=Field(ge=0,le=10**12)

@router.post("/agents/{agent_id}/agreements",status_code=201)
def agreement_create(agent_id:str,body:ContractIn,
        db:Session=Depends(get_db),user:User=Depends(admin)):
    a=agent_guard(db,user,agent_id,True)
    old=db.scalar(select(AgentAgreement).where(
        AgentAgreement.tenant_id==user.tenant_id,AgentAgreement.agent_id==a.id,
        AgentAgreement.contract_key==body.contract_key))
    if old:
        actual=(old.jurisdiction,old.currency,old.scope,old.max_budget_minor)
        expected=(body.jurisdiction,body.currency,body.scope,body.max_budget_minor)
        if actual!=expected:raise HTTPException(409,"Agreement idempotency conflict")
        return {**contract_view(old),"reused":True}
    if db.scalar(select(AgentAgreement.id).where(
        AgentAgreement.tenant_id==user.tenant_id,
        AgentAgreement.agent_id==a.id,
        AgentAgreement.status==ACTIVE_AGREEMENT).limit(1)):
        raise HTTPException(409,"Suspend active agreement before replacement")
    obj=AgentAgreement(tenant_id=user.tenant_id,agent_id=a.id,
        **body.model_dump(),status="draft")
    db.add(obj);db.flush();log(db,user,obj,"agent_agreement_drafted",a.id);db.commit()
    return {**contract_view(obj),"reused":False}

@router.get("/agents/{agent_id}/agreements")
def agreements(agent_id:str,db:Session=Depends(get_db),user:User=Depends(admin)):
    a=own(db,user,AgentProfile,agent_id)
    xs=db.scalars(select(AgentAgreement).where(
        AgentAgreement.tenant_id==user.tenant_id,
        AgentAgreement.agent_id==a.id).order_by(AgentAgreement.created_at.desc()).limit(100)).all()
    return {"items":[contract_view(x) for x in xs]}

class ReviewIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["administratively_reviewed","rejected","suspended"]
    document_reference:str=Field(min_length=6,max_length=100,pattern=REF)

@router.post("/agreements/{agreement_id}/review")
def agreement_review(agreement_id:str,body:ReviewIn,
        db:Session=Depends(get_db),user:User=Depends(admin)):
    # Lock the agent before agreement to serialize activation/suspension.
    candidate=own(db,user,AgentAgreement,agreement_id)
    a=agent_guard(db,user,candidate.agent_id,True)
    x=own(db,user,AgentAgreement,agreement_id,True)
    if x.status=="draft" and body.decision in ("administratively_reviewed","rejected"):
        pass
    elif x.status=="administratively_reviewed" and body.decision=="suspended":
        pass
    else:raise HTTPException(409,"Invalid agreement state transition")
    if body.decision==ACTIVE_AGREEMENT:
        existing=db.scalar(select(AgentAgreement.id).where(
            AgentAgreement.tenant_id==user.tenant_id,
            AgentAgreement.agent_id==a.id,
            AgentAgreement.status==ACTIVE_AGREEMENT,
            AgentAgreement.id!=x.id).limit(1))
        if existing:raise HTTPException(409,"Another agreement already active")
    x.status=body.decision;x.document_reference=body.document_reference
    x.reviewed_by=user.id
    log(db,user,x,"agent_agreement_"+body.decision,a.id);db.commit()
    return contract_view(x)

class AccountIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:EmailStr
    password:str=Field(min_length=16,max_length=128)

@router.post("/agents/{agent_id}/account",status_code=201)
def provision_account(agent_id:str,body:AccountIn,
        db:Session=Depends(get_db),user:User=Depends(admin)):
    a=agent_guard(db,user,agent_id,True)
    contract_guard(db,user,a.id)
    if db.scalar(select(AgentIdentity.id).where(
        AgentIdentity.tenant_id==user.tenant_id,AgentIdentity.agent_id==a.id).limit(1)):
        raise HTTPException(409,"Agent already has a portal account")
    email=str(body.email).strip().lower()
    if db.scalar(select(User.id).where(User.tenant_id==user.tenant_id,User.email==email).limit(1)):
        raise HTTPException(409,"Email already exists in tenant")
    account=User(tenant_id=user.tenant_id,email=email,
        password_hash=password_hash(body.password),role="agent",active=True)
    db.add(account);db.flush()
    link=AgentIdentity(tenant_id=user.tenant_id,agent_id=a.id,
        user_id=account.id,provisioned_by=user.id)
    db.add(link);db.flush();log(db,user,link,"agent_account_provisioned",a.id)
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,"Duplicate agent portal mapping")
    return {"id":link.id,"user_id":account.id,"email":email,
            "role":"agent","agent_id":a.id,"password_returned":False}

@router.post("/agents/{agent_id}/disable")
def disable_agent(agent_id:str,db:Session=Depends(get_db),user:User=Depends(admin)):
    a=own(db,user,AgentProfile,agent_id,True)
    a.active=False
    linked=db.scalars(select(AgentIdentity).where(
        AgentIdentity.tenant_id==user.tenant_id,
        AgentIdentity.agent_id==a.id)).all()
    for item in linked:
        account=own(db,user,User,item.user_id,True)
        account.active=False
        now=datetime.now(timezone.utc)
        sessions=db.scalars(select(RefreshSession).where(
            RefreshSession.tenant_id==user.tenant_id,
            RefreshSession.user_id==account.id,
            RefreshSession.revoked_at.is_(None))).all()
        for s in sessions:s.revoked_at=now
    log(db,user,a,"agent_disabled",a.id)
    db.commit()
    return {"id":a.id,"active":False,"linked_accounts_disabled":len(linked)}

class IntentIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=8,max_length=100,pattern=KEY)
    channel:Literal["web","whatsapp","telegram","offline"]
    campaign_code:str=Field(min_length=3,max_length=60,pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,59}$")

@router.post("/portal/referrals",status_code=201)
def submit_intent(body:IntentIn,db:Session=Depends(get_db),user:User=Depends(agent_role)):
    a,_=portal_identity(db,user)
    a=agent_guard(db,user,a.id,True)
    agreement=contract_guard(db,user,a.id)
    old=db.scalar(select(AgentReferralIntent).where(
        AgentReferralIntent.tenant_id==user.tenant_id,
        AgentReferralIntent.agent_id==a.id,
        AgentReferralIntent.request_key==body.request_key))
    if old:
        if (old.channel,old.campaign_code)!=(body.channel,body.campaign_code) or old.status=="blocked":
            raise HTTPException(409,"Referral request-key conflict")
        return {**intent_view(old),"reused":True}
    obj=AgentReferralIntent(tenant_id=user.tenant_id,agent_id=a.id,agreement_id=agreement.id,
        **body.model_dump(),status="submitted")
    db.add(obj);db.flush();log(db,user,obj,"agent_referral_submitted",a.id);db.commit()
    return {**intent_view(obj),"reused":False}

@router.get("/portal/me")
def portal_me(db:Session=Depends(get_db),user:User=Depends(agent_role)):
    a,_=portal_identity(db,user)
    agreement=contract_guard(db,user,a.id)
    return {"agent_id":a.id,"agent_name":a.name,"country":a.country,
        "agreement_status":agreement.status,"referral_code":a.referral_code,
        "allowed_patient_records":0,"clinical_data_access":False,
        "commission_payments_enabled":False}

@router.get("/portal/referrals")
def portal_referrals(db:Session=Depends(get_db),user:User=Depends(agent_role)):
    a,_=portal_identity(db,user)
    contract_guard(db,user,a.id)
    xs=db.scalars(select(AgentReferralIntent).where(
        AgentReferralIntent.tenant_id==user.tenant_id,
        AgentReferralIntent.agent_id==a.id).order_by(
            AgentReferralIntent.created_at.desc()).limit(100)).all()
    return {"items":[intent_view(x) for x in xs],"medical_information_included":False}

@router.get("/agents/{agent_id}/referrals")
def admin_referrals(agent_id:str,db:Session=Depends(get_db),user:User=Depends(admin)):
    a=own(db,user,AgentProfile,agent_id)
    xs=db.scalars(select(AgentReferralIntent).where(
        AgentReferralIntent.tenant_id==user.tenant_id,
        AgentReferralIntent.agent_id==a.id).order_by(
            AgentReferralIntent.created_at.desc()).limit(100)).all()
    return {"items":[{**intent_view(x),"patient_id":x.patient_id,
        "matched_by":x.matched_by} for x in xs]}

class MatchIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    patient_id:str

@router.post("/referrals/{intent_id}/attribute")
def attribute(intent_id:str,body:MatchIn,
        db:Session=Depends(get_db),user:User=Depends(admin)):
    candidate=own(db,user,AgentReferralIntent,intent_id)
    a=agent_guard(db,user,candidate.agent_id,True)
    contract_guard(db,user,a.id)
    x=own(db,user,AgentReferralIntent,intent_id,True)
    if x.status!="submitted":raise HTTPException(409,"Attribution already recorded or blocked")
    patient=own(db,user,Patient,body.patient_id)
    if not active_consent(db,user.tenant_id,patient.id,"intake") or not active_consent(
        db,user.tenant_id,patient.id,"agent_referral"):
        raise HTTPException(409,"Patient intake and specific agent referral consent required")
    prior=db.scalar(select(AgentReferralIntent.id).where(
        AgentReferralIntent.tenant_id==user.tenant_id,
        AgentReferralIntent.patient_id==patient.id).limit(1))
    if prior:raise HTTPException(409,"Patient already attributed to agent referral")
    # Direct legacy lead attribution remains prohibited, as it skips consent.
    lead=LeadSource(tenant_id=user.tenant_id,patient_id=patient.id,
        agent_id=a.id,source="agent_portal",campaign=x.campaign_code)
    x.status="attributed";x.patient_id=patient.id;x.matched_by=user.id
    db.add(lead);db.flush();log(db,user,x,"agent_referral_attributed",a.id)
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,"Duplicate referral attribution")
    return {"id":x.id,"status":x.status,"patient_id":patient.id,
            "consent_verified_at_action":True,"no_patient_details_sent_to_agent":True}

class CommercialIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    draft_key:str=Field(min_length=8,max_length=100,pattern=KEY)
    agreement_id:str
    activity_reference:str=Field(min_length=6,max_length=100,pattern=REF)
    amount_minor:int=Field(gt=0,le=10**12)

@router.post("/agents/{agent_id}/commercial-drafts",status_code=201)
def commercial_draft(agent_id:str,body:CommercialIn,
        db:Session=Depends(get_db),user:User=Depends(admin)):
    a=agent_guard(db,user,agent_id,True)
    agreement=contract_guard(db,user,a.id,True)
    if body.agreement_id!=agreement.id:
        raise HTTPException(409,"Only active reviewed agreement permitted")
    old=db.scalar(select(AgentCommercialDraft).where(
        AgentCommercialDraft.tenant_id==user.tenant_id,
        AgentCommercialDraft.agent_id==a.id,
        AgentCommercialDraft.draft_key==body.draft_key))
    if old:
        if (old.activity_reference,old.amount_minor,old.agreement_id)!=(
            body.activity_reference,body.amount_minor,body.agreement_id):
            raise HTTPException(409,"Commercial draft key conflict")
        return {**commercial_view(old),"reused":True}
    total=db.scalar(select(func.coalesce(func.sum(AgentCommercialDraft.amount_minor),0)).where(
        AgentCommercialDraft.tenant_id==user.tenant_id,
        AgentCommercialDraft.agreement_id==agreement.id,
        AgentCommercialDraft.status=="blocked_legal_review"))
    if int(total)+body.amount_minor>agreement.max_budget_minor:
        raise HTTPException(409,"Draft commercial budget cap exceeded")
    obj=AgentCommercialDraft(tenant_id=user.tenant_id,agent_id=a.id,
        **body.model_dump(),status="blocked_legal_review")
    db.add(obj);db.flush();log(db,user,obj,"agent_commercial_draft_blocked",a.id)
    db.commit()
    return {**commercial_view(obj),"reused":False}

@router.get("/agents/{agent_id}/commercial-drafts")
def commercial_drafts(agent_id:str,db:Session=Depends(get_db),user:User=Depends(admin)):
    a=own(db,user,AgentProfile,agent_id)
    xs=db.scalars(select(AgentCommercialDraft).where(
        AgentCommercialDraft.tenant_id==user.tenant_id,
        AgentCommercialDraft.agent_id==a.id).order_by(
            AgentCommercialDraft.created_at.desc()).limit(100)).all()
    return {"items":[commercial_view(x) for x in xs],
            "payouts_enabled":False,"legal_review_required":True,
            "per_patient_commissions_enabled":False}

@router.get("/agents/{agent_id}/history")
def history(agent_id:str,db:Session=Depends(get_db),user:User=Depends(admin)):
    a=own(db,user,AgentProfile,agent_id)
    xs=db.scalars(select(AgentGovernanceEvent).where(
        AgentGovernanceEvent.tenant_id==user.tenant_id,
        AgentGovernanceEvent.agent_id==a.id).order_by(
            AgentGovernanceEvent.created_at.desc()).limit(200)).all()
    return {"items":[{"event":x.action,"actor_id":x.actor_id,
             "entity_kind":x.entity_kind,"entity_id":x.entity_id,
             "created_at":x.created_at} for x in xs]}
