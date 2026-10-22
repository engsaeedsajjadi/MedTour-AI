"""Development-only, tenant-isolated Patient CRM administrative coordination.

No clinical recommendations, automated outreach, or destructive patient merge.
The duplicate detector is an exact contact-identifier hint, never proof that
two people have the same identity.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .enterprise_models import CRMFollowUp, CRMDuplicateReview, CaseTimeline, LeadSource
from .models import Patient, Case, User, Audit
from .security import roles
from .safety_rules import active_consent

router = APIRouter(prefix="/api/v1/crm", tags=["patient CRM"])
staff = roles("admin", "operator")
admin = roles("admin")
REF = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
REASONS = {"document_reminder", "appointment_coordination", "travel_coordination", "check_in", "general_administrative"}
OUTCOMES = {"contact_attempted", "human_contact_completed", "no_response", "no_longer_needed"}


def now():
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timezone offset required")
    return value.astimezone(timezone.utc)


def patient_case(db: Session, user: User, case_id: str) -> tuple[Case, Patient]:
    case = db.scalar(select(Case).where(
        Case.id == case_id, Case.tenant_id == user.tenant_id,
    ))
    if case is None:
        raise HTTPException(404, "Case not found")
    patient = db.scalar(select(Patient).where(
        Patient.id == case.patient_id, Patient.tenant_id == user.tenant_id,
    ))
    if patient is None:
        raise HTTPException(404, "Patient not found")
    return case, patient


def owned_patient(db: Session, user: User, patient_id: str) -> Patient:
    patient = db.scalar(select(Patient).where(
        Patient.id == patient_id, Patient.tenant_id == user.tenant_id,
    ))
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient


def eligible_user(db: Session, user: User, user_id: str) -> User:
    target = db.scalar(select(User).where(
        User.tenant_id == user.tenant_id, User.id == user_id,
        User.active.is_(True), User.role.in_(("admin", "operator")),
    ))
    if target is None:
        raise HTTPException(404, "Active coordinator not found")
    return target


def audit(db: Session, user: User, event: str, kind: str, entity: str):
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event=event, entity_type=kind, entity_id=entity,
    ))


def timeline(db: Session, user: User, case_id: str, event: str, detail: str):
    db.add(CaseTimeline(
        tenant_id=user.tenant_id, case_id=case_id, actor_id=user.id,
        event=event, details=detail,
    ))


def followup_view(row: CRMFollowUp) -> dict:
    return {
        "id": row.id, "case_id": row.case_id, "patient_id": row.patient_id,
        "assigned_user_id": row.assigned_user_id, "due_at": row.due_at,
        "reason_code": row.reason_code, "status": row.status,
        "outcome_code": row.outcome_code, "created_at": row.created_at,
        "resolved_at": row.resolved_at,
        # Never include raw notes, contacts or treatment data.
    }


class AssignIn(BaseModel):
    coordinator_user_id: str


@router.post("/cases/{case_id}/assign")
def assign_case(
    case_id: str, body: AssignIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    case, patient = patient_case(db, user, case_id)
    eligible_user(db, user, body.coordinator_user_id)
    case = db.scalar(select(Case).where(
        Case.id == case.id, Case.tenant_id == user.tenant_id,
    ).with_for_update())
    if case.assigned_operator_id != body.coordinator_user_id:
        previous = case.assigned_operator_id
        case.assigned_operator_id = body.coordinator_user_id
        audit(db, user, "crm_case_assigned", "Case", case.id)
        timeline(db, user, case.id, "crm_owner_changed",
                 "assigned_by_admin;previous="+str(previous or "unassigned")+
                 ";next="+body.coordinator_user_id)
        db.commit()
    return {"case_id": case.id, "coordinator_user_id": case.assigned_operator_id,
            "external_message_sent": False}


@router.post("/patients/{patient_id}/assign")
def assign_patient(
    patient_id: str, body: AssignIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    patient = owned_patient(db, user, patient_id)
    eligible_user(db, user, body.coordinator_user_id)
    patient = db.scalar(select(Patient).where(
        Patient.id == patient.id, Patient.tenant_id == user.tenant_id,
    ).with_for_update())
    if patient.owner_user_id != body.coordinator_user_id:
        patient.owner_user_id = body.coordinator_user_id
        audit(db, user, "crm_patient_owner_changed", "Patient", patient.id)
        db.commit()
    return {"patient_id": patient.id, "coordinator_user_id": patient.owner_user_id,
            "external_message_sent": False}


class FollowUpIn(BaseModel):
    case_id: str
    assigned_user_id: str
    due_at: datetime
    reason_code: Literal[
        "document_reminder", "appointment_coordination", "travel_coordination",
        "check_in", "general_administrative",
    ]
    idempotency_key: str = Field(
        min_length=8, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$",
    )

    @field_validator("due_at")
    @classmethod
    def validate_due_date(cls, value: datetime):
        utc = as_utc(value)
        if not now()-timedelta(minutes=5) <= utc <= now()+timedelta(days=180):
            raise ValueError("Due date must fall within 5 minutes ago to 180 days ahead")
        return utc


@router.post("/followups", status_code=201)
def schedule_followup(
    body: FollowUpIn,
    db: Session = Depends(get_db), user: User = Depends(staff),
):
    case, patient = patient_case(db, user, body.case_id)
    if case.status in ("closed", "cancelled"):
        raise HTTPException(409, "Cannot schedule follow-up on inactive case")
    if not active_consent(db, user.tenant_id, patient.id, "communication"):
        raise HTTPException(409, "Current communication consent required")
    eligible_user(db, user, body.assigned_user_id)
    db.scalar(select(Case.id).where(
        Case.id == case.id, Case.tenant_id == user.tenant_id
    ).with_for_update())
    existing = db.scalar(select(CRMFollowUp).where(
        CRMFollowUp.tenant_id == user.tenant_id,
        CRMFollowUp.case_id == case.id,
        CRMFollowUp.idempotency_key == body.idempotency_key,
    ))
    if existing:
        if (existing.patient_id != patient.id or
            existing.assigned_user_id != body.assigned_user_id or
            existing.reason_code != body.reason_code or
            as_utc(existing.due_at) != body.due_at):
            raise HTTPException(409, "Idempotency key already used for different follow-up")
        return {**followup_view(existing), "reused": True, "automated_send": False}
    entry = CRMFollowUp(
        tenant_id=user.tenant_id, case_id=case.id, patient_id=patient.id,
        assigned_user_id=body.assigned_user_id, created_by=user.id,
        due_at=body.due_at, reason_code=body.reason_code,
        idempotency_key=body.idempotency_key, status="open",
    )
    db.add(entry)
    db.flush()
    audit(db, user, "crm_followup_scheduled", "CRMFollowUp", entry.id)
    timeline(db, user, case.id, "crm_followup_scheduled",
             "followup="+entry.id+";reason="+body.reason_code)
    db.commit()
    return {**followup_view(entry), "reused": False, "automated_send": False}


@router.get("/followups")
def list_followups(
    status: Literal["open","completed","cancelled","blocked"] | None = None,
    overdue_only: bool = False,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(staff),
):
    q = select(CRMFollowUp).where(CRMFollowUp.tenant_id == user.tenant_id)
    if user.role != "admin":
        q = q.where(CRMFollowUp.assigned_user_id == user.id)
    if status:
        q = q.where(CRMFollowUp.status == status)
    if overdue_only:
        q = q.where(CRMFollowUp.status == "open", CRMFollowUp.due_at <= now())
    q = q.order_by(CRMFollowUp.due_at.asc(), CRMFollowUp.id).limit(limit)
    return {
        "items": [followup_view(row) for row in db.scalars(q).all()],
        "automated_messages": False, "raw_patient_contacts_included": False,
    }


class ResolveIn(BaseModel):
    action: Literal["complete", "cancel"]
    outcome_code: Literal[
        "contact_attempted", "human_contact_completed", "no_response",
        "no_longer_needed",
    ] | None = None
    reference: str | None = Field(
        default=None, min_length=6, max_length=100, pattern=REF,
    )


@router.post("/followups/{followup_id}/resolve")
def resolve_followup(
    followup_id: str, body: ResolveIn,
    db: Session = Depends(get_db), user: User = Depends(staff),
):
    row = db.scalar(select(CRMFollowUp).where(
        CRMFollowUp.id == followup_id,
        CRMFollowUp.tenant_id == user.tenant_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Follow-up not found")
    if user.role != "admin" and row.assigned_user_id != user.id:
        raise HTTPException(403, "Follow-up is not assigned to this operator")
    case, patient = patient_case(db, user, row.case_id)
    if case.patient_id != row.patient_id:
        raise HTTPException(409, "Follow-up is inconsistent with case")
    if row.status != "open":
        raise HTTPException(409, "Follow-up cannot be resolved again")
    if body.action == "complete":
        if not active_consent(db, user.tenant_id, patient.id, "communication"):
            raise HTTPException(409, "Current communication consent required")
        if not body.outcome_code or not body.reference:
            raise HTTPException(422, "Manual follow-up outcome and reference required")
        row.status = "completed"
        row.outcome_code = body.outcome_code
        row.completion_reference = body.reference
    else:
        if body.outcome_code or body.reference:
            raise HTTPException(422, "Cancelled follow-up cannot carry a contact outcome")
        row.status = "cancelled"
    row.resolved_at = now()
    audit(db, user, "crm_followup_"+row.status, "CRMFollowUp", row.id)
    timeline(db, user, case.id, "crm_followup_"+row.status,
             "followup="+row.id+";manual_only")
    db.commit()
    return {**followup_view(row), "contact_verified_externally": False}


def normalized_contact(value: str) -> str | None:
    # International phone-like identifiers only; do not infer unique identity.
    if not re.fullmatch(r"\+?[\d ()-]{8,25}", value.strip(), re.ASCII):
        return None
    digits = "".join(c for c in value if c in "0123456789")
    return digits if 8 <= len(digits) <= 15 else None


@router.get("/patients/{patient_id}/duplicates")
def duplicate_candidates(
    patient_id: str,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    target = owned_patient(db, user, patient_id)
    normalized = normalized_contact(target.contact or "")
    if not normalized:
        return {"candidates": [], "matching_basis": "unavailable",
                "identity_verified": False, "automatic_merge": False}
    # Bounded indexed tenant listing at alpha scale. Not a global search.
    rows = db.scalars(select(Patient).where(
        Patient.tenant_id == user.tenant_id,
        Patient.id != target.id,
    ).order_by(Patient.id).limit(500)).all()
    matches = [row for row in rows
               if normalized_contact(row.contact or "") == normalized]
    return {
        "candidates": [{"patient_id": x.id, "basis": "exact_normalized_contact"}
                       for x in matches[:25]],
        "matching_basis": "exact_normalized_contact_only",
        "identity_verified": False, "automatic_merge": False,
        "search_bounded": True,
    }


class DuplicateReviewIn(BaseModel):
    candidate_patient_id: str
    decision: Literal["possible_same", "distinct"]
    reference: str = Field(min_length=6, max_length=100, pattern=REF)


@router.post("/patients/{patient_id}/duplicate-review")
def review_duplicate(
    patient_id: str, body: DuplicateReviewIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    left = owned_patient(db, user, patient_id)
    right = owned_patient(db, user, body.candidate_patient_id)
    if left.id == right.id:
        raise HTTPException(422, "Cannot compare patient with self")
    if (not normalized_contact(left.contact or "") or
        normalized_contact(left.contact or "") != normalized_contact(right.contact or "")):
        raise HTTPException(409, "No exact contact match: use independent identity review")
    low, high = sorted((left.id, right.id))
    existing = db.scalar(select(CRMDuplicateReview).where(
        CRMDuplicateReview.tenant_id == user.tenant_id,
        CRMDuplicateReview.left_patient_id == low,
        CRMDuplicateReview.right_patient_id == high,
    ).with_for_update())
    if existing:
        if existing.decision != body.decision or existing.evidence_reference != body.reference:
            raise HTTPException(409, "Prior duplicate decision exists; separate review required")
        return {"id":existing.id,"decision":existing.decision,"reused":True,
                "patient_records_merged":False,"clinical_identity_verified":False}
    event = CRMDuplicateReview(
        tenant_id=user.tenant_id, left_patient_id=low, right_patient_id=high,
        decision=body.decision, evidence_reference=body.reference,
        reviewer_user_id=user.id,
    )
    db.add(event)
    db.flush()
    audit(db, user, "crm_duplicate_review_recorded", "CRMDuplicateReview", event.id)
    db.commit()
    return {"id":event.id,"decision":event.decision,"reused":False,
            "patient_records_merged":False,"clinical_identity_verified":False}


@router.get("/patients/{patient_id}/overview")
def patient_overview(
    patient_id: str,
    db: Session = Depends(get_db), user: User = Depends(staff),
):
    patient = owned_patient(db, user, patient_id)
    cases = db.scalars(select(Case).where(
        Case.tenant_id == user.tenant_id, Case.patient_id == patient.id,
    ).order_by(Case.created_at.desc()).limit(100)).all()
    lead_sources = db.scalars(select(LeadSource).where(
        LeadSource.tenant_id == user.tenant_id,
        LeadSource.patient_id == patient.id,
    ).order_by(LeadSource.created_at.desc()).limit(25)).all()
    followups = db.scalars(select(CRMFollowUp).where(
        CRMFollowUp.tenant_id == user.tenant_id,
        CRMFollowUp.patient_id == patient.id,
    ).order_by(CRMFollowUp.due_at.desc()).limit(100)).all()
    return {
        "patient_id": patient.id, "language": patient.language,
        "owner_user_id": patient.owner_user_id,
        "cases": [{"id":x.id,"status":x.status,
                   "assigned_operator_id":x.assigned_operator_id}
                  for x in cases],
        "lead_sources": [{"source":x.source,"campaign":x.campaign}
                         for x in lead_sources],
        "communication_consent": active_consent(
            db, user.tenant_id, patient.id, "communication"),
        "open_followups": len([x for x in followups if x.status=="open"]),
        "automatic_outreach_enabled":False,
        "no_medical_notes_included":True,
    }
