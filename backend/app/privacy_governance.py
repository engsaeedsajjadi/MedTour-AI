"""Section 28: tenant-bound data subject request registry, no automated PHI export/deletion."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from .database import Base, get_db
from .models import TenantEntity, Patient, User, Audit
from .security import roles

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy governance"])
ADMIN = roles("admin")

class PrivacyRequest(TenantEntity, Base):
    __tablename__ = "privacy_requests"
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    request_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending_identity", nullable=False)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

class OpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str
    request_type: Literal["access", "rectification", "erasure", "restriction", "portability"]

class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["identity_verified", "rejected", "legal_hold", "closed_manual"]

def public(row: PrivacyRequest) -> dict:
    return {"id":row.id,"patient_id":row.patient_id,"request_type":row.request_type,
            "status":row.status,"created_at":row.created_at,
            "automatic_export_or_deletion":False}

def log(db, user, row, event):
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event=event,
                 entity_type="PrivacyRequest",entity_id=row.id))

@router.post("/requests",status_code=201)
def create_request(body:OpenRequest, db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    patient=db.scalar(select(Patient.id).where(Patient.id==body.patient_id,
                                               Patient.tenant_id==user.tenant_id))
    if not patient: raise HTTPException(404,"Patient not found")
    row=PrivacyRequest(tenant_id=user.tenant_id,patient_id=body.patient_id,
                       request_type=body.request_type,requested_by=user.id)
    db.add(row);db.flush()
    log(db,user,row,"privacy_request_opened")
    db.commit();db.refresh(row)
    return public(row)

@router.get("/requests")
def list_requests(limit:int=Query(50,ge=1,le=100),
                  db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    rows=db.scalars(select(PrivacyRequest).where(
        PrivacyRequest.tenant_id==user.tenant_id).order_by(
        PrivacyRequest.created_at.desc(),PrivacyRequest.id.desc()).limit(limit)).all()
    return {"items":[public(row) for row in rows]}

@router.get("/requests/{request_id}")
def get_request(request_id:str,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    row=db.scalar(select(PrivacyRequest).where(PrivacyRequest.id==request_id,
                                      PrivacyRequest.tenant_id==user.tenant_id))
    if row is None:raise HTTPException(404,"Request not found")
    return public(row)

@router.post("/requests/{request_id}/review")
def review(request_id:str,body:ReviewRequest,db:Session=Depends(get_db),
           user:User=Depends(ADMIN)):
    row=db.scalar(select(PrivacyRequest).where(
        PrivacyRequest.id==request_id,PrivacyRequest.tenant_id==user.tenant_id
    ).with_for_update())
    if row is None:raise HTTPException(404,"Request not found")
    allowed={
        "pending_identity":{"identity_verified":"pending_legal_review","rejected":"rejected"},
        "pending_legal_review":{"legal_hold":"legal_hold","closed_manual":"closed_manual","rejected":"rejected"},
        "legal_hold":{"closed_manual":"closed_manual"},
    }
    next_status=allowed.get(row.status,{}).get(body.decision)
    if not next_status:raise HTTPException(409,"Invalid privacy request transition")
    # No operation here mutates patient data, exports PHI, or treats a checklist as identity proof.
    row.status=next_status;row.reviewed_by=user.id
    log(db,user,row,"privacy_request_"+body.decision)
    db.commit();db.refresh(row)
    return public(row)
