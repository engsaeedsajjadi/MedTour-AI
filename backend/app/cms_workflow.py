"""Section 23: tenant-scoped, versioned CMS with independent review quorum.

Internal administrative approvals ONLY. A role is not verified professional
medical/legal/translation certification. No real PHI or production legal
attestation; no external workflow, signing or legal advice.
"""
from __future__ import annotations

import hashlib,re
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,EmailStr,Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .enterprise_models import ContentPage,CmsVersion,CmsReview,CmsWorkflowEvent
from .models import User,Audit
from .security import roles,password_hash

router=APIRouter(prefix="/api/v1/cms/workflow",tags=["versioned cms governance"])
STAGES={"translation":"cms_translator","medical":"cms_medical_reviewer",
        "legal":"cms_legal_reviewer"}
EDIT_ROLES=roles("admin","cms_editor")
VIEW_ROLES=roles("admin","cms_editor",*STAGES.values())
MANAGER=roles("admin")
SLUGS=frozenset(("about","services","process","faq","contact","privacy","terms","medical-disclaimer"))

def digest(title:str,body:str):
    return hashlib.sha256((title+"\x00"+body).encode("utf-8")).hexdigest()

def owned(db,user,model,id,lock=False):
    q=select(model).where(model.tenant_id==user.tenant_id,model.id==id)
    x=db.scalar(q.with_for_update() if lock else q)
    if not x:raise HTTPException(404,"CMS resource not found")
    return x

def latest(db,user,page):
    return db.scalar(select(CmsVersion).where(CmsVersion.tenant_id==user.tenant_id,
        CmsVersion.page_id==page.id).order_by(CmsVersion.version_no.desc()).limit(1))

def page_state(db,user,page):
    newest=latest(db,user,page)
    reviews=db.scalars(select(CmsReview).where(
        CmsReview.tenant_id==user.tenant_id,
        CmsReview.version_id==newest.id)).all() if newest else []
    decisions={a.stage:a.decision for a in reviews}
    return {
        "id":page.id,"slug":page.slug,"locale":page.locale,
        "status":page.status,
        "published_version_no":page.published_version_no,
        "latest_version":newest.version_no if newest else 0,
        "latest_version_id":newest.id if newest else None,
        "latest_state":newest.status if newest else "unversioned",
        "latest_content_hash":newest.content_hash if newest else None,
        "review_stages":{key:decisions.get(key,"pending") for key in STAGES},
        "external_credentials_verified":False,
        "content_medically_or_legally_independently_certified":False,
    }

def add_event(db,user,page,version,action,reference="internal"):
    db.add(CmsWorkflowEvent(tenant_id=user.tenant_id,page_id=page.id,
        version_id=version.id if version else None,actor_id=user.id,
        action=action,reference=reference))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event=action,
        entity_type="ContentPage",entity_id=page.id))

def initialize_version(db,user,page,reason="initial_content"):
    if latest(db,user,page):
        return latest(db,user,page)
    v=CmsVersion(tenant_id=page.tenant_id,page_id=page.id,version_no=1,
        title=page.title,body=page.body,content_hash=digest(page.title,page.body),
        author_id=user.id,reason=reason,status="draft")
    db.add(v);db.flush()
    add_event(db,user,page,v,"cms_version_initialized")
    return v

class ReviewerAccount(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:EmailStr
    password:str=Field(min_length=16,max_length=128)
    role:Literal["cms_editor","cms_translator","cms_medical_reviewer",
                 "cms_legal_reviewer"]

@router.post("/reviewers",status_code=201)
def create_reviewer(body:ReviewerAccount,db:Session=Depends(get_db),
                    user:User=Depends(MANAGER)):
    email=str(body.email).strip().lower()
    if db.scalar(select(User.id).where(
        User.tenant_id==user.tenant_id,User.email==email).limit(1)):
        raise HTTPException(409,"Account email already registered")
    obj=User(tenant_id=user.tenant_id,email=email,
        password_hash=password_hash(body.password),role=body.role,active=True)
    db.add(obj);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="cms_reviewer_account_created",entity_type="User",entity_id=obj.id))
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,"Account already provisioned")
    return {"id":obj.id,"email":obj.email,"role":obj.role,
        "credentials_independently_verified":False,"password_returned":False}

class RevisionIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    title:str=Field(min_length=2,max_length=250)
    body:str=Field(min_length=1,max_length=30000)
    expected_version:int=Field(ge=0)
    reason:str=Field(min_length=6,max_length=200)

def make_revision(db,user,page,body:RevisionIn):
    current=latest(db,user,page)
    number=current.version_no if current else 0
    if number!=body.expected_version:
        raise HTTPException(409,"Stale CMS version; reload before saving")
    name=body.title.strip();content=body.body.strip()
    if len(name)<2 or not content:raise HTTPException(422,"Empty content not allowed")
    if current and current.content_hash==digest(name,content):
        raise HTTPException(409,"No content changes; no new version created")
    if current and current.status not in ("published","superseded","rejected"):
        current.status="superseded"
    obj=CmsVersion(tenant_id=user.tenant_id,page_id=page.id,
        version_no=number+1,title=name,body=content,
        content_hash=digest(name,content),author_id=user.id,
        reason=body.reason,status="draft")
    db.add(obj);db.flush()
    add_event(db,user,page,obj,"cms_revision_created")
    db.commit()
    return version_public(obj)

def version_public(v):
    return {"id":v.id,"page_id":v.page_id,"version_no":v.version_no,
        "title":v.title,"body":v.body,"content_hash":v.content_hash,
        "reason":v.reason,"author_id":v.author_id,"status":v.status,
        "created_at":v.created_at}

@router.get("/pages")
def pages(db:Session=Depends(get_db),user:User=Depends(VIEW_ROLES),
          limit:int=Query(100,ge=1,le=200)):
    ps=db.scalars(select(ContentPage).where(
        ContentPage.tenant_id==user.tenant_id).order_by(
        ContentPage.created_at.desc()).limit(limit)).all()
    return {"items":[page_state(db,user,p) for p in ps],
        "independent_medical_legal_certification":False}

@router.get("/pages/{page_id}/versions")
def versions(page_id:str,db:Session=Depends(get_db),user:User=Depends(VIEW_ROLES)):
    page=owned(db,user,ContentPage,page_id)
    xs=db.scalars(select(CmsVersion).where(
        CmsVersion.tenant_id==user.tenant_id,
        CmsVersion.page_id==page.id).order_by(CmsVersion.version_no.desc()).limit(100)).all()
    return {"page":page_state(db,user,page),"items":[version_public(v) for v in xs]}

@router.post("/pages/{page_id}/versions",status_code=201)
def revise(page_id:str,body:RevisionIn,db:Session=Depends(get_db),
           user:User=Depends(EDIT_ROLES)):
    page=owned(db,user,ContentPage,page_id,True)
    return make_revision(db,user,page,body)

@router.post("/pages/{page_id}/submit")
def submit(page_id:str,db:Session=Depends(get_db),
           user:User=Depends(EDIT_ROLES)):
    page=owned(db,user,ContentPage,page_id,True)
    v=latest(db,user,page)
    if not v or v.status!="draft":
        raise HTTPException(409,"Only latest draft can be submitted for review")
    if v.author_id!=user.id and user.role!="admin":
        raise HTTPException(403,"Only author or administrator may submit")
    v.status="in_review"
    add_event(db,user,page,v,"cms_revision_submitted")
    db.commit()
    return {"version_id":v.id,"version_no":v.version_no,"status":v.status}

class DecisionIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["approved","rejected"]
    evidence_reference:str=Field(min_length=6,max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$")

@router.post("/pages/{page_id}/reviews/{stage}")
def review(page_id:str,stage:str,body:DecisionIn,
           db:Session=Depends(get_db),user:User=Depends(VIEW_ROLES)):
    if stage not in STAGES:raise HTTPException(422,"Unknown review stage")
    if user.role!=STAGES[stage]:raise HTTPException(403,"Independent specialist role required")
    page=owned(db,user,ContentPage,page_id,True)
    v=latest(db,user,page)
    if not v or v.status!="in_review":
        raise HTTPException(409,"Latest revision not under review")
    if user.id==v.author_id:
        raise HTTPException(409,"Author cannot approve own content")
    prior=db.scalars(select(CmsReview).where(CmsReview.tenant_id==user.tenant_id,
        CmsReview.version_id==v.id)).all()
    if any(x.stage==stage for x in prior):
        raise HTTPException(409,"Review already recorded; use a new revision")
    if any(x.reviewer_id==user.id for x in prior):
        raise HTTPException(409,"Review stages require distinct human actors")
    x=CmsReview(tenant_id=user.tenant_id,version_id=v.id,stage=stage,
        decision=body.decision,reviewer_id=user.id,evidence_reference=body.evidence_reference)
    db.add(x);db.flush()
    if body.decision=="rejected":
        v.status="rejected"
    elif ({x.stage for x in prior if x.decision=="approved"} | {stage}) == set(STAGES):
        # explicit parentheses below keep stage-set comparison unambiguous
        v.status="ready"
    add_event(db,user,page,v,"cms_review_"+stage+"_"+body.decision,body.evidence_reference)
    db.commit()
    return {"page_id":page.id,"version_id":v.id,"stage":stage,
        "decision":body.decision,"version_state":v.status,
        "external_reviewer_credentials_verified":False}

@router.post("/pages/{page_id}/publish")
def publish(page_id:str,db:Session=Depends(get_db),user:User=Depends(MANAGER)):
    page=owned(db,user,ContentPage,page_id,True)
    v=latest(db,user,page)
    if not v or v.status!="ready":
        raise HTTPException(409,"Translation, medical and legal reviews required on latest version")
    approvals=db.scalars(select(CmsReview).where(CmsReview.tenant_id==user.tenant_id,
        CmsReview.version_id==v.id,CmsReview.decision=="approved")).all()
    if {a.stage for a in approvals}!=set(STAGES) or len({a.reviewer_id for a in approvals})!=3:
        raise HTTPException(409,"Three distinct approved stages required")
    if any(a.reviewer_id==v.author_id for a in approvals):
        raise HTTPException(409,"Author cannot be a reviewer")
    if any(a.reviewer_id==user.id for a in approvals):
        raise HTTPException(409,"Publisher must be separate from reviewers")
    v.status="published"
    page.title=v.title;page.body=v.body;page.status="published"
    page.published_version_no=v.version_no;page.approved_by=user.id
    add_event(db,user,page,v,"cms_version_published")
    db.commit()
    return {"id":page.id,"status":"published","version_no":v.version_no,
        "content_hash":v.content_hash,"human_review_count":3,
        "legal_or_medical_credentials_independently_verified":False}

@router.get("/pages/{page_id}/history")
def history(page_id:str,db:Session=Depends(get_db),user:User=Depends(VIEW_ROLES)):
    page=owned(db,user,ContentPage,page_id)
    xs=db.scalars(select(CmsWorkflowEvent).where(
        CmsWorkflowEvent.tenant_id==user.tenant_id,
        CmsWorkflowEvent.page_id==page.id).order_by(
            CmsWorkflowEvent.created_at.desc()).limit(200)).all()
    return {"items":[{"id":x.id,"version_id":x.version_id,
        "action":x.action,"actor_id":x.actor_id,
        "reference":x.reference,"created_at":x.created_at} for x in xs]}

class RestoreIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_version:int=Field(ge=0)
    reason:str=Field(min_length=6,max_length=200)

@router.post("/pages/{page_id}/versions/{version_id}/restore",status_code=201)
def restore(page_id:str,version_id:str,body:RestoreIn,
            db:Session=Depends(get_db),user:User=Depends(EDIT_ROLES)):
    page=owned(db,user,ContentPage,page_id,True)
    prior=owned(db,user,CmsVersion,version_id)
    if prior.page_id!=page.id:raise HTTPException(404,"Revision not found for page")
    current=latest(db,user,page)
    if not current or prior.id==current.id:
        raise HTTPException(409,"Select an older revision to restore")
    draft=RevisionIn(title=prior.title,body=prior.body,
        expected_version=body.expected_version,reason=body.reason)
    v=make_revision(db,user,page,draft)
    return {**v,"restored_from":prior.version_no,"reviews_reset":True,
        "publication_changed":False}
