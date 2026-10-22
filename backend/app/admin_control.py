"""Tenant-restricted administrative control center (synthetic alpha only).

Read models intentionally exclude raw conversations, medical notes, documents,
contact details, provider secrets and staff credential hashes. Counts are
database-derived, not live external delivery/provider confirmations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .database import get_db
from .enterprise_models import (
    CRMFollowUp, PatientIntake, Operation, OutboundMessage,
    TranslationDraft, CaseTimeline, IntakeReviewerAssignment,
)
from .models import (
    Audit, Case, Conversation, Patient, Quote, User,
)
from .security import roles
from .safety_rules import active_consent

router = APIRouter(prefix="/api/v1/admin-center", tags=["administrative control center"])
administrator = roles("admin")
QUEUE_TYPES = frozenset({
    "urgent_intake", "review_intake", "followup_overdue",
    "operation_review", "quote_approval", "human_handoff",
})
OPEN_OPERATIONS = ("requested", "in_review", "awaiting_external")
MAX_QUEUE_SCAN = 250


def count(db: Session, model, tenant_id: str, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(
        model.tenant_id == tenant_id, *conditions,
    )) or 0


@router.get("/summary")
def summary(
    db: Session = Depends(get_db), user: User = Depends(administrator),
):
    tenant = user.tenant_id
    moment = datetime.now(timezone.utc)
    cases_by_status = db.execute(select(Case.status, func.count(Case.id)).where(
        Case.tenant_id == tenant
    ).group_by(Case.status)).all()
    return {
        "patients": count(db, Patient, tenant),
        "cases": count(db, Case, tenant),
        "active_cases": count(db, Case, tenant,
                             Case.status.notin_(("closed", "cancelled"))),
        "cases_by_status": {status: amount for status, amount in cases_by_status},
        "staff_active": count(db, User, tenant, User.active.is_(True)),
        "open_followups": count(db, CRMFollowUp, tenant,
                                CRMFollowUp.status == "open"),
        "overdue_followups": count(db, CRMFollowUp, tenant,
                                   CRMFollowUp.status == "open",
                                   CRMFollowUp.due_at <= moment),
        "pending_operations": count(db, Operation, tenant,
                                    Operation.status.in_(OPEN_OPERATIONS)),
        "draft_quotes": count(db, Quote, tenant, Quote.status == "draft"),
        "human_handoffs": count(db, Conversation, tenant,
                                Conversation.human_handoff.is_(True)),
        "urgent_intake_flags": db.scalar(
            select(func.count(func.distinct(PatientIntake.case_id))).where(
                PatientIntake.tenant_id == tenant,
                PatientIntake.status == "requires_urgent_human_review",
            )
        ) or 0,
        "pending_translations": count(db, TranslationDraft, tenant,
                                       TranslationDraft.status == "pending_review"),
        "outbound_needs_human_approval": count(
            db, OutboundMessage, tenant, OutboundMessage.status == "pending_approval",
        ),
        "external_providers_live_verified": False,
        "medical_approvals_supported": False,
        "real_patient_data_allowed": False,
        "metrics_source": "tenant_database",
    }


def queue_item(category: str, record_id: str, case_id: str | None,
               created_at: datetime, status: str, destination: str) -> dict:
    return {
        "category": category, "id": record_id, "case_id": case_id,
        "status": status, "created_at": created_at,
        "priority": "urgent" if category == "urgent_intake"
                    else "high" if category in ("review_intake", "followup_overdue")
                    else "normal",
        "destination": destination,
        "automatic_decision": False,
    }


@router.get("/queue")
def action_queue(
    category: Literal[
        "urgent_intake", "review_intake", "followup_overdue",
        "operation_review", "quote_approval", "human_handoff",
    ] | None = None,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(administrator),
):
    tenant = user.tenant_id
    moment = datetime.now(timezone.utc)
    results = []
    if category is None or category in ("urgent_intake", "review_intake"):
        sessions = db.scalars(select(PatientIntake).where(
            PatientIntake.tenant_id == tenant,
        ).order_by(PatientIntake.created_at.desc(), PatientIntake.id.desc())
                             .limit(MAX_QUEUE_SCAN)).all()
        most_recent = {}
        urgent = {}
        for session in sessions:
            most_recent.setdefault(session.case_id, session)
            if session.status == "requires_urgent_human_review":
                urgent.setdefault(session.case_id, session)
        if category != "review_intake":
            for c, session in urgent.items():
                results.append(queue_item(
                    "urgent_intake", session.id, c, session.created_at,
                    session.status, "/intake-review",
                ))
        if category != "urgent_intake":
            for c, session in most_recent.items():
                if c not in urgent and session.status == "awaiting_clinician_review":
                    results.append(queue_item(
                        "review_intake", session.id, c, session.created_at,
                        session.status, "/intake-clinician",
                    ))
    if category is None or category == "followup_overdue":
        followups = db.scalars(select(CRMFollowUp).where(
            CRMFollowUp.tenant_id == tenant, CRMFollowUp.status == "open",
            CRMFollowUp.due_at <= moment,
        ).order_by(CRMFollowUp.due_at, CRMFollowUp.id).limit(MAX_QUEUE_SCAN)).all()
        for row in followups:
            results.append(queue_item(
                "followup_overdue", row.id, row.case_id, row.due_at,
                row.status, "/crm",
            ))
    if category is None or category == "operation_review":
        operations = db.scalars(select(Operation).where(
            Operation.tenant_id == tenant,
            Operation.status.in_(OPEN_OPERATIONS),
        ).order_by(Operation.created_at, Operation.id)
                                .limit(MAX_QUEUE_SCAN)).all()
        for row in operations:
            results.append(queue_item(
                "operation_review", row.id, row.case_id, row.created_at,
                row.status, "/operations",
            ))
    if category is None or category == "quote_approval":
        quotes = db.scalars(select(Quote).where(
            Quote.tenant_id == tenant, Quote.status == "draft",
        ).order_by(Quote.created_at, Quote.id).limit(MAX_QUEUE_SCAN)).all()
        for row in quotes:
            results.append(queue_item(
                "quote_approval", row.id, row.case_id, row.created_at,
                row.status, "/quotations",
            ))
    if category is None or category == "human_handoff":
        conversations = db.scalars(select(Conversation).where(
            Conversation.tenant_id == tenant,
            Conversation.human_handoff.is_(True),
        ).order_by(Conversation.created_at, Conversation.id)
                                    .limit(MAX_QUEUE_SCAN)).all()
        for row in conversations:
            # Conversations are patient-scoped, not necessarily one case.
            # Never guess a case_id from the patient.
            results.append(queue_item(
                "human_handoff", row.id, None, row.created_at,
                "human_handoff", "/conversations",
            ))
    priority = {"urgent": 0, "high": 1, "normal": 2}
    results.sort(key=lambda row: (
        priority[row["priority"]], row["created_at"], row["id"]
    ))
    return {
        "items": results[:limit], "limit": limit,
        "scan_bounded": True, "max_scan_per_category": MAX_QUEUE_SCAN,
        "total_matches_exhaustive": False,
        "medical_content_included": False, "external_actions_triggered": False,
    }


def escaped_fragment(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search")
def administrative_search(
    q: str = Query(min_length=3, max_length=80),
    domain: Literal["all", "patients", "cases", "operations"] = "all",
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(administrator),
):
    term = q.strip()
    if len(term) < 3:
        raise HTTPException(422, "At least three characters are required")
    like = "%" + escaped_fragment(term) + "%"
    tenant = user.tenant_id
    results = []
    if domain in ("all", "patients"):
        patients = db.scalars(select(Patient).where(
            Patient.tenant_id == tenant,
            or_(Patient.id.ilike(like, escape="\\"),
                Patient.full_name.ilike(like, escape="\\")),
        ).order_by(Patient.id).limit(limit)).all()
        results += [{
            "type": "patient", "id": p.id, "label": p.full_name,
            "patient_id": p.id, "case_id": None,
            "destination": "/crm",
        } for p in patients]
    if domain in ("all", "cases"):
        cases = db.scalars(select(Case).where(
            Case.tenant_id == tenant,
            or_(Case.id.ilike(like, escape="\\"),
                Case.patient_id.ilike(like, escape="\\"),
                Case.status.ilike(like, escape="\\")),
        ).order_by(Case.id).limit(limit)).all()
        results += [{
            "type": "case", "id": c.id, "label": c.status,
            "patient_id": c.patient_id, "case_id": c.id,
            "destination": "/journey",
        } for c in cases]
    if domain in ("all", "operations"):
        ops = db.scalars(select(Operation).where(
            Operation.tenant_id == tenant,
            or_(Operation.id.ilike(like, escape="\\"),
                Operation.kind.ilike(like, escape="\\"),
                Operation.status.ilike(like, escape="\\")),
        ).order_by(Operation.id).limit(limit)).all()
        results += [{
            "type": "operation", "id": o.id, "label": o.kind,
            "patient_id": o.patient_id, "case_id": o.case_id,
            "destination": "/operations",
        } for o in ops]
    return {
        "items": results[:limit], "limited": True,
        "medical_content_included": False,
        "contacts_included": False, "sensitive_operational_notes_included": False,
    }


@router.get("/cases/{case_id}/overview")
def case_overview(
    case_id: str, db: Session = Depends(get_db),
    user: User = Depends(administrator),
):
    case = db.scalar(select(Case).where(
        Case.id == case_id, Case.tenant_id == user.tenant_id,
    ))
    if case is None:
        raise HTTPException(404, "Case not found")
    patient = db.scalar(select(Patient).where(
        Patient.tenant_id == user.tenant_id, Patient.id == case.patient_id,
    ))
    if patient is None:
        raise HTTPException(404, "Patient not found")
    operations = db.scalars(select(Operation).where(
        Operation.tenant_id == user.tenant_id,
        Operation.case_id == case.id,
    ).order_by(Operation.created_at.desc()).limit(50)).all()
    followups = db.scalars(select(CRMFollowUp).where(
        CRMFollowUp.tenant_id == user.tenant_id,
        CRMFollowUp.case_id == case.id,
        CRMFollowUp.patient_id == patient.id,
    ).order_by(CRMFollowUp.due_at.desc()).limit(50)).all()
    # Scope to the current case only; avoid raw clinical data entirely.
    return {
        "case_id": case.id,
        "patient_id": patient.id,
        "status": case.status,
        "assigned_operator_id": case.assigned_operator_id,
        "communication_consent": active_consent(
            db, user.tenant_id, patient.id, "communication"),
        "intake_consent": active_consent(
            db, user.tenant_id, patient.id, "intake"),
        "open_followups": sum(1 for x in followups if x.status == "open"),
        "pending_operations": sum(1 for x in operations if x.status in OPEN_OPERATIONS),
        "lists_bounded": True,
        "clinical_review_approved": False,
        "medical_records_included": False,
    }


@router.post("/staff/{staff_id}/deactivate")
def deactivate_staff(
    staff_id: str, db: Session = Depends(get_db),
    user: User = Depends(administrator),
):
    if staff_id == user.id:
        raise HTTPException(409, "Administrator cannot deactivate own account")
    target = db.scalar(select(User).where(
        User.tenant_id == user.tenant_id,
        User.id == staff_id,
    ).with_for_update())
    if target is None:
        raise HTTPException(404, "Staff account not found")
    if not target.active:
        return {"staff_id": target.id, "active": False, "reused": True}
    # Fail-closed until every assigned workload is explicitly reassigned.
    if (
        count(db, CRMFollowUp, user.tenant_id,
              CRMFollowUp.assigned_user_id == target.id,
              CRMFollowUp.status == "open")
        or count(db, Case, user.tenant_id,
                 Case.assigned_operator_id == target.id,
                 Case.status.notin_(("closed", "cancelled")))
        or count(db, Patient, user.tenant_id,
                 Patient.owner_user_id == target.id)
        or count(db, Operation, user.tenant_id,
                 Operation.assigned_to == target.id,
                 Operation.status.in_(OPEN_OPERATIONS))
        or count(db, Conversation, user.tenant_id,
                 Conversation.assigned_user_id == target.id)
        or count(db, IntakeReviewerAssignment, user.tenant_id,
                 IntakeReviewerAssignment.reviewer_user_id == target.id,
                 IntakeReviewerAssignment.active.is_(True))
    ):
        raise HTTPException(409, "Reassign all active work before deactivation")
    target.active = False
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event="admin_center_staff_deactivated", entity_type="User",
        entity_id=target.id,
    ))
    db.commit()
    return {"staff_id": target.id, "active": False, "reused": False,
            "tokens_invalidated_by_active_account_check": True}
