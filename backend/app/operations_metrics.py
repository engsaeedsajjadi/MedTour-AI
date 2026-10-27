"""Section 41: bounded, metadata-only operational metrics for internal administrators.

No metrics endpoint on standalone public webhook gateways. Aggregates are
tenant-scoped; never include patient IDs, message bodies or provider tokens.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .enterprise_models import OutboundMessage
from .security import roles

router=APIRouter(prefix="/api/v1/operations-metrics",tags=["internal operations metrics"])
ADMIN=roles("admin")
STATES=("pending_approval","approved","sending","sent","delivered","read","needs_reconciliation","rejected","cancelled")

@router.get("/outbox")
def outbox(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    counts={status:0 for status in STATES}
    results=db.execute(select(OutboundMessage.status,func.count()).where(
        OutboundMessage.tenant_id==user.tenant_id
    ).group_by(OutboundMessage.status)).all()
    unknown=0
    for status,total in results:
        if status in counts:counts[status]=int(total)
        else:unknown+=int(total)
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=15)
    overdue=int(db.scalar(select(func.count()).select_from(OutboundMessage).where(
        OutboundMessage.tenant_id==user.tenant_id,
        OutboundMessage.status=="approved",
        OutboundMessage.created_at<cutoff)) or 0)
    return {"source":"tenant_db","counts":counts,"other_count":unknown,
            "approved_older_than_15m":overdue,
            "queue_delivery_health_verified":False,"production_slo_met":False,
            "contains_patient_data":False}
