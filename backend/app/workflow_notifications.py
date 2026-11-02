"""Section 30: internal staff notification inbox. No external delivery or PHI."""
from __future__ import annotations
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Audit
from .enterprise_models import Notification
from .security import current_user,roles

router=APIRouter(prefix="/api/v1/workflow-notifications",tags=["internal staff workflows"])
ADMIN=roles("admin")

class NoticeIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    recipient_id:str
    kind:str=Field(pattern=r"^(task_review|case_action_required|system_update)$")
    # Never accept freeform medical messages in the notification body.
    reference_id:str=Field(min_length=1,max_length=100,pattern=r"^[A-Za-z0-9_-]+$")

LABELS={
    "task_review":"A staff task needs review",
    "case_action_required":"A case requires staff action",
    "system_update":"An internal system update is available",
}

def view(n):
    return {"id":n.id,"recipient_id":n.recipient_id,"title":n.title,
            "read":n.read_at is not None,"created_at":n.created_at}

@router.post("",status_code=201)
def create(body:NoticeIn,db:Session=Depends(get_db),admin:User=Depends(ADMIN)):
    recipient=db.scalar(select(User).where(User.id==body.recipient_id,
        User.tenant_id==admin.tenant_id,User.active.is_(True)))
    if not recipient:raise HTTPException(404,"Recipient not found")
    n=Notification(tenant_id=admin.tenant_id,recipient_id=recipient.id,
                   title=LABELS[body.kind],body="")
    db.add(n);db.flush()
    db.add(Audit(tenant_id=admin.tenant_id,user_id=admin.id,
        event="internal_staff_notification_created",entity_type="Notification",entity_id=n.id))
    db.commit();db.refresh(n)
    return view(n)|{"external_delivery":False,"reference_in_message":False}

@router.get("")
def inbox(limit:int=Query(50,ge=1,le=100),unread_only:bool=False,
          db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=select(Notification).where(Notification.tenant_id==user.tenant_id,
                                 Notification.recipient_id==user.id)
    if unread_only:q=q.where(Notification.read_at.is_(None))
    items=db.scalars(q.order_by(Notification.created_at.desc(),Notification.id.desc()).limit(limit)).all()
    return {"items":[view(n) for n in items],"external_delivery":False}

@router.post("/{notice_id}/read")
def mark_read(notice_id:str,db:Session=Depends(get_db),
              user:User=Depends(current_user)):
    n=db.scalar(select(Notification).where(Notification.id==notice_id,
        Notification.tenant_id==user.tenant_id,Notification.recipient_id==user.id)
        .with_for_update())
    if n is None:raise HTTPException(404,"Notification not found")
    if n.read_at is None:
        n.read_at=datetime.now(timezone.utc)
        db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
            event="internal_staff_notification_read",entity_type="Notification",entity_id=n.id))
        db.commit()
    return view(n)
