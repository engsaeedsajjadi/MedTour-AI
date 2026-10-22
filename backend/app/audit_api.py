"""Read-only, tenant-scoped audit feed.

Intentionally omits raw request bodies, clinical records, credentials and secrets.
This endpoint is a development capability, not evidence of immutable audit storage.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Audit, User
from .security import roles

router = APIRouter(prefix="/api/v1", tags=["Audit"])
audit_reader = roles("admin", "auditor")


@router.get("/audit-events")
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
    user: User = Depends(audit_reader),
):
    # Tenant restriction is mandatory even for admin and auditor.
    rows = db.scalars(
        select(Audit)
        .where(Audit.tenant_id == user.tenant_id)
        .order_by(Audit.created_at.desc(), Audit.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "event": row.event,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "user_id": row.user_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]
