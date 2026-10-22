"""Administrative cross-module case workspace.

All reads are staff-authorized and explicitly tenant+case scoped. No notes,
conversation text, medical answers, patient contacts, filenames or secrets
are included in this read model. It is NOT a medical record or clinical decision.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    User, Case, Patient, Consent, Document, Referral, Appointment, Quote,
    TravelRequest, Conversation, Task, Audit,
)
from .enterprise_models import Operation, PatientIntake, CaseTimeline, MoneyEntry
from .security import roles
from .case_mission import mission_evidence

router = APIRouter(prefix="/api/v1/modules", tags=["enterprise module coordination"])
staff = roles("admin", "operator")
manager = roles("admin")

# This is a CAPABILITY REGISTRY, not a claim that these domains are finished.
# A separate master-prompt section owns each domain's acceptance requirements.
MODULES = (
    ("patients", "بیماران", "/patients", "local_workflow", 9),
    ("cases", "پرونده‌ها", "/cases", "local_workflow", 9),
    ("intake", "پذیرش چندزبانه", "/journey", "partial", 7),
    ("documents", "مدارک امن", "/secure-documents", "external_gate", 8),
    ("physicians", "پزشکان و ارجاع", "/providers", "partial", 12),
    ("hospitals", "مراکز درمانی", "/hospitals", "partial", 13),
    ("appointments", "نوبت‌ها", "/appointments", "partial", 15),
    ("quotes", "پیش‌فاکتورها", "/quotations", "partial", 16),
    ("travel", "سفر و ویزا", "/travel", "external_gate", 17),
    ("services", "هماهنگی خدمات", "/operations", "partial", 19),
    ("conversations", "مکالمات", "/conversations", "external_gate", 11),
    ("agents", "نمایندگان", "/agents", "partial", 20),
    ("finance", "مالی", "/finance", "partial", 29),
    ("website", "وب‌سایت عمومی", "/cms", "partial", 22),
    ("knowledge", "پایگاه دانش", "/knowledge", "partial", 23),
    ("notifications", "اعلان‌ها", "/messaging", "partial", 30),
    ("analytics", "گزارش‌ها", "/reports", "partial", 31),
    ("subscriptions", "اشتراک SaaS", "/settings", "not_delivered", 37),
    ("voice", "پیام صوتی", "/settings", "not_delivered", 25),
)

MODEL_BY_MODULE = {
    "patients": Patient,
    "cases": Case,
    "intake": PatientIntake,
    "documents": Document,
    "physicians": Referral,
    "appointments": Appointment,
    "quotes": Quote,
    "travel": TravelRequest,
    "services": Operation,
    "conversations": Conversation,
}

CASE_MODELS = (
    ("intake", PatientIntake),
    ("documents", Document),
    ("physicians", Referral),
    ("appointments", Appointment),
    ("quotes", Quote),
    ("travel", TravelRequest),
    ("services", Operation),
    ("tasks", Task),
)

def owned_case(db: Session, case_id: str, user: User) -> Case:
    case = db.scalar(
        select(Case).where(
            Case.id == case_id, Case.tenant_id == user.tenant_id
        )
    )
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


def count_for_case(db: Session, model, tenant_id: str, case_id: str) -> int:
    return int(db.scalar(
        select(func.count()).select_from(model).where(
            model.tenant_id == tenant_id,
            model.case_id == case_id,
        )
    ) or 0)


@router.get("")
def module_catalog(user: User = Depends(staff)):
    # Accessible routes are staff views; an external integration is never
    # considered live based on a catalog entry.
    return {
        "production_ready": False,
        "tenant_scoped": True,
        "external_services_verified": False,
        "modules": [
            {"key": key, "label": label, "route": route,
             "status": status, "master_section": section}
            for key, label, route, status, section in MODULES
        ],
    }


@router.get("/cases/{case_id}")
def case_workspace(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    case = owned_case(db, case_id, user)
    tid = user.tenant_id
    counts = {
        key: count_for_case(db, model, tid, case.id)
        for key, model in CASE_MODELS
    }
    # A conversation is scoped by tenant AND the patient from the owned case.
    counts["conversations"] = int(db.scalar(
        select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == tid,
            Conversation.patient_id == case.patient_id,
        )
    ) or 0)
    counts["tasks_open"] = int(db.scalar(
        select(func.count()).select_from(Task).where(
            Task.tenant_id == tid, Task.case_id == case.id,
            Task.status == "open",
        )
    ) or 0)

    tasks = db.scalars(
        select(Task).where(
            Task.tenant_id == tid, Task.case_id == case.id,
        ).order_by(Task.created_at.desc(), Task.id.desc()).limit(100)
    ).all()
    # Task titles are operational notes and may unintentionally contain PHI.
    # Return only opaque identifiers and administrative states.
    safe_tasks = [
        {"id": task.id, "status": task.status, "created_at": task.created_at}
        for task in tasks
    ]
    mission = mission_evidence(db, case)
    return {
        "case_id": case.id,
        "status": case.status,
        "specialty": case.specialty,
        "counts": counts,
        "tasks": safe_tasks,
        "tasks_truncated": counts["tasks"] > len(safe_tasks),
        "readiness": mission["conditions"],
        "urgent_intake_detected": mission["signals"]["urgent_intake_detected"],
        "production_ready": False,
        "note": (
            "Administrative read model with recorded statuses only. "
            "No diagnosis, real booking or independent confirmation."
        ),
    }


class TaskStateChange(BaseModel):
    status: Literal["open", "done"]
    # Administrative attestation only. No patient medical notes.
    reference: str = Field(min_length=6, max_length=100,
                           pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$")


@router.patch("/cases/{case_id}/tasks/{task_id}/status")
def update_task(
    case_id: str,
    task_id: str,
    body: TaskStateChange,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    case = owned_case(db, case_id, user)
    task = db.scalar(
        select(Task).where(
            Task.tenant_id == user.tenant_id,
            Task.case_id == case.id,
            Task.id == task_id,
        )
    )
    if task is None:
        raise HTTPException(404, "Task not found")
    if task.status not in ("open", "done") or task.status == body.status:
        raise HTTPException(409, "Invalid or redundant task transition")
    # Compare-and-swap to prevent two concurrent workers/requests overwriting
    # the same administrative transition or duplicating audit events.
    changed = db.execute(update(Task).where(
        Task.id == task_id,
        Task.tenant_id == user.tenant_id,
        Task.case_id == case.id,
        Task.status == task.status,
    ).values(status=body.status).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Concurrent task update; reload case")

    db.add(CaseTimeline(
        tenant_id=user.tenant_id, case_id=case.id, actor_id=user.id,
        event="task_status_changed",
        details=f"task={task_id};to={body.status};reference={body.reference}",
    ))
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event="case_task_state_changed", entity_type="Task",
        entity_id=task_id,
    ))
    db.commit()
    return {"id": task_id, "case_id": case.id, "status": body.status,
            "audit_recorded": True, "external_confirmation": False}


@router.get("/summary")
def module_summary(
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    # Bounded aggregation across staff tenant only. No PHI or financial
    # figures exposed, and no inference of external provider availability.
    counts = {}
    for key, model in (
        ("patients", Patient), ("cases", Case), ("tasks", Task),
        ("documents", Document), ("appointments", Appointment),
        ("quotes", Quote), ("travel", TravelRequest), ("services", Operation),
    ):
        counts[key] = int(db.scalar(select(func.count()).select_from(model).where(
            model.tenant_id == user.tenant_id
        )) or 0)
    return {"counts": counts, "tenant_scoped": True,
            "external_confirmations_verified": False,
            "production_ready": False}
