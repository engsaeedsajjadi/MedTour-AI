"""Section 37 internal SaaS entitlements: no payment activation or real billing."""
from __future__ import annotations
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict
from sqlalchemy import String,ForeignKey,UniqueConstraint,select
from sqlalchemy.orm import Mapped,mapped_column,Session
from .database import Base,get_db
from .models import TenantEntity,User,Audit
from .security import roles

PLANS={
    "starter":{"max_staff":3,"max_cases":100,"ai_enabled":False},
    "professional":{"max_staff":15,"max_cases":1000,"ai_enabled":False},
    "enterprise":{"max_staff":100,"max_cases":10000,"ai_enabled":False},
}
router=APIRouter(prefix="/api/v1/saas",tags=["development subscription management"])
ADMIN=roles("admin")

class TenantSubscription(TenantEntity,Base):
    __tablename__="tenant_subscriptions"
    plan_code:Mapped[str]=mapped_column(String(32),nullable=False)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default="evaluation")
    granted_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    __table_args__=(UniqueConstraint("tenant_id",name="uq_tenant_subscription"),)

class PlanChange(BaseModel):
    model_config=ConfigDict(extra="forbid")
    plan_code:str

@router.get("/plans")
def plans():
    return {"plans":[{"code":name,**limits} for name,limits in PLANS.items()],
            "published_prices":False,"purchase_available":False}

@router.get("/subscription")
def current(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    row=db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id==user.tenant_id))
    return {"tenant_id":user.tenant_id,"plan":row.plan_code if row else None,
            "status":row.status if row else "not_configured",
            "limits":PLANS[row.plan_code] if row else None,
            "payment_verified":False,"billing_enabled":False,
            "entitlements_enforced_globally":False}

@router.post("/subscription/evaluation")
def evaluation(body:PlanChange,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if body.plan_code not in PLANS:raise HTTPException(422,"Unknown plan")
    row=db.scalar(select(TenantSubscription).where(
        TenantSubscription.tenant_id==user.tenant_id).with_for_update())
    if row:raise HTTPException(409,"Subscription exists; upgrade requires verified billing workflow")
    row=TenantSubscription(tenant_id=user.tenant_id,plan_code=body.plan_code,
                           status="evaluation",granted_by=user.id)
    db.add(row);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="saas_evaluation_created",
                 entity_type="TenantSubscription",entity_id=row.id))
    db.commit()
    return {"id":row.id,"plan":row.plan_code,"status":row.status,
            "charged":False,"automated_renewal":False}
