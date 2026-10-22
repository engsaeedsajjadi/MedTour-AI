"""Administrative medical-intake coordination, not a diagnosis or clinical approval.

Existing case, intake, audit and timeline tables are reused; no migration.
Only a qualified, independently verified clinician can make actual clinical
decisions. Role/administrative handoff alone does not prove such verification.
"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Audit, Case, Patient, User
from .enterprise_models import CaseTimeline, PatientIntake
from .security import roles
from .safety_rules import active_consent
from .intake import LANGUAGES, QUESTION_KEYS

router = APIRouter(prefix="/api/v1/intake-coordination", tags=["intake coordination"])
staff = roles("admin", "operator")

SUBMITTED = frozenset(("awaiting_clinician_review", "handoff_recorded"))
BLOCKED = frozenset(("requires_urgent_human_review",))
RESTARTABLE = frozenset(("needs_more_information",))


def latest_intake(db: Session, tenant_id: str, case_id: str) -> PatientIntake | None:
    return db.scalar(
        select(PatientIntake)
        .where(PatientIntake.tenant_id == tenant_id, PatientIntake.case_id == case_id)
        .order_by(PatientIntake.created_at.desc(), PatientIntake.id.desc())
        .limit(1)
    )


def prepare_intake_start(db: Session, case: Case, language: str) -> tuple[PatientIntake, bool]:
    """Serialize creation per case on PostgreSQL, prohibit urgent-session bypass.

    The calling endpoint must commit the new row when created.
    """
    if language not in LANGUAGES:
        raise HTTPException(422, "Unsupported language")
    # Serializes independently initiated staff/patient starts in PostgreSQL.
    db.scalar(select(Case.id).where(
        Case.id == case.id, Case.tenant_id == case.tenant_id
    ).with_for_update())
    last = latest_intake(db, case.tenant_id, case.id)
    if last:
        if last.status == "in_progress":
            if last.language != language:
                raise HTTPException(409, "An intake is already in progress in another language")
            return last, False
        if last.status in BLOCKED:
            raise HTTPException(409, "Urgent flag requires qualified human review; do not restart")
        if last.status in SUBMITTED:
            raise HTTPException(409, "Intake is already awaiting external clinical review")
        if last.status not in RESTARTABLE:
            raise HTTPException(409, "Intake cannot be restarted in this status")
    row = PatientIntake(tenant_id=case.tenant_id, case_id=case.id, language=language)
    db.add(row)
    db.flush()
    return row, True


def intake_snapshot(row: PatientIntake) -> dict:
    return {
        "id": row.id,
        "case_id": row.case_id,
        "language": row.language,
        "status": row.status,
        "stage": row.stage,
        "questions_total": len(QUESTION_KEYS),
        "remaining_questions": max(len(QUESTION_KEYS) - row.stage, 0),
        "human_clinical_decision_recorded": False,
    }


@router.get("/queue")
def intake_queue(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    # Only opaque case/session IDs and stages; NO raw answers, contacts or notes.
    rows = db.scalars(select(PatientIntake).where(
        PatientIntake.tenant_id == user.tenant_id
    ).order_by(PatientIntake.created_at.desc(), PatientIntake.id.desc()).limit(500)).all()
    seen = set()
    results = []
    for row in rows:
        if row.case_id in seen:
            continue
        seen.add(row.case_id)
        if row.status in ("awaiting_clinician_review", "requires_urgent_human_review"):
            results.append({
                **intake_snapshot(row),
                "urgency_keyword_alert": row.status == "requires_urgent_human_review",
                "clinical_validation": "not_performed",
            })
        if len(results) >= limit:
            break
    return {
        "items": results,
        "scan_bounded": True,
        "no_phi_returned": True,
        "medical_decisions_supported": False,
    }


@router.get("/cases/{case_id}")
def case_intake_status(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    case = db.scalar(select(Case).where(
        Case.id == case_id, Case.tenant_id == user.tenant_id
    ))
    if case is None:
        raise HTTPException(404, "Case not found")
    consent = active_consent(db, user.tenant_id, case.patient_id, "intake")
    row = latest_intake(db, user.tenant_id, case.id)
    return {
        "case_id": case.id,
        "consent_active": consent,
        "current": intake_snapshot(row) if row else None,
        "urgency_keyword_alert": bool(row and row.status in BLOCKED),
        "ready_for_administrative_handoff": bool(
            consent and row and row.status == "awaiting_clinician_review"
        ),
        "clinical_validation": "not_performed",
        "next_action": (
            "urgent_external_care" if row and row.status in BLOCKED
            else "obtain_intake_consent" if not consent
            else "record_administrative_handoff" if row and row.status == "awaiting_clinician_review"
            else "resume_or_start_intake"
        ),
    }


class AdministrativeReview(BaseModel):
    action: Literal["request_more_information", "record_handoff"]
    reference: str = Field(
        min_length=6, max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$",
    )


@router.post("/sessions/{session_id}/review")
def intake_review(
    session_id: str,
    body: AdministrativeReview,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    # Administrative staff can return incomplete questionnaires for a new
    # submission or document an external handoff; never mark clinical approval.
    row = db.scalar(select(PatientIntake).where(
        PatientIntake.id == session_id,
        PatientIntake.tenant_id == user.tenant_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Intake not found")
    case = db.scalar(select(Case).where(
        Case.id == row.case_id,
        Case.tenant_id == user.tenant_id,
    ))
    if case is None:
        raise HTTPException(404, "Case not found")
    if not active_consent(db, user.tenant_id, case.patient_id, "intake"):
        raise HTTPException(409, "Active intake consent required")
    if row.status in BLOCKED:
        raise HTTPException(409, "Urgent medical alert cannot be cleared by administrative review")
    if row.status != "awaiting_clinician_review":
        raise HTTPException(409, "Only submitted intake can be administratively reviewed")
    if body.action == "record_handoff" and user.role != "admin":
        raise HTTPException(403, "Administrator must attest handoff reference")
    before = row.status
    row.status = (
        "needs_more_information" if body.action == "request_more_information"
        else "handoff_recorded"
    )
    db.add(CaseTimeline(
        tenant_id=user.tenant_id, case_id=row.case_id, actor_id=user.id,
        event="intake_administrative_review",
        details=(
            f"session={row.id};from={before};to={row.status};"
            f"reference={body.reference}"
        ),
    ))
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event="intake_administrative_review_recorded",
        entity_type="PatientIntake", entity_id=row.id,
    ))
    db.commit()
    return {
        **intake_snapshot(row),
        "administrative_action": body.action,
        "clinical_decision": False,
        "external_clinician_confirmed": False,
    }
