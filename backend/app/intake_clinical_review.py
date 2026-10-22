"""Section 07: auditable, least-privilege intake review and urgent escalation.

Only administrative recommendations and contact *attempts* are recorded.
A role or locally attested credential is NOT independent licensure, clinical
safety approval, diagnosis or proof an emergency responder was contacted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import Audit, Case, User
from .enterprise_models import (
    CaseTimeline, IntakeReviewRecord, IntakeReviewerAssignment,
    PatientIntake, ReviewerCredential,
)
from .security import roles
from .safety_rules import active_consent
from .intake_coordination import latest_intake

router = APIRouter(prefix="/api/v1/intake-review", tags=["intake reviewer and safety"])
staff = roles("admin", "operator")
admin = roles("admin")
physician = roles("physician")
REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"


def _now():
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _session(db: Session, tenant: str, pk: str, lock: bool = False) -> PatientIntake:
    query = select(PatientIntake).where(
        PatientIntake.id == pk, PatientIntake.tenant_id == tenant
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        raise HTTPException(404, "Intake not found")
    case = db.scalar(select(Case).where(
        Case.id == row.case_id, Case.tenant_id == tenant
    ))
    if not case:
        raise HTTPException(404, "Case not found")
    # Prevent actions on stale sessions even if status was already submitted.
    if latest_intake(db, tenant, case.id).id != row.id:
        raise HTTPException(409, "Superseded intake cannot be reviewed")
    if not active_consent(db, tenant, case.patient_id, "intake"):
        raise HTTPException(409, "Active intake consent required")
    return row


def _credential(db: Session, user: User) -> ReviewerCredential:
    row = db.scalar(select(ReviewerCredential).where(
        ReviewerCredential.tenant_id == user.tenant_id,
        ReviewerCredential.user_id == user.id,
        ReviewerCredential.status == "locally_attested",
    ))
    if not row or _utc(row.expires_at) <= _now():
        raise HTTPException(403, "Current locally attested reviewer credential required")
    return row


def _assignment(db: Session, session: PatientIntake, reviewer: User):
    result = db.scalar(select(IntakeReviewerAssignment).where(
        IntakeReviewerAssignment.tenant_id == reviewer.tenant_id,
        IntakeReviewerAssignment.intake_id == session.id,
        IntakeReviewerAssignment.case_id == session.case_id,
        IntakeReviewerAssignment.reviewer_user_id == reviewer.id,
        IntakeReviewerAssignment.active.is_(True),
    ))
    if result is None:
        raise HTTPException(403, "Reviewer is not assigned to this intake")
    return result


def _record(db: Session, session: PatientIntake, actor: User, action: str, reference: str):
    existing = db.scalar(select(IntakeReviewRecord).where(
        IntakeReviewRecord.tenant_id == actor.tenant_id,
        IntakeReviewRecord.intake_id == session.id,
        IntakeReviewRecord.action == action,
        IntakeReviewRecord.reference == reference,
    ))
    if existing:
        return existing, False
    record = IntakeReviewRecord(
        tenant_id=actor.tenant_id, case_id=session.case_id, intake_id=session.id,
        actor_id=actor.id, action=action, reference=reference,
        external_confirmation=False,
    )
    db.add(record)
    db.flush()
    db.add(Audit(
        tenant_id=actor.tenant_id, user_id=actor.id,
        event="intake_review_metadata_recorded",
        entity_type="IntakeReviewRecord", entity_id=record.id,
    ))
    db.add(CaseTimeline(
        tenant_id=actor.tenant_id, case_id=session.case_id, actor_id=actor.id,
        event="intake_review_metadata_recorded",
        details=f"session={session.id};action={action};reference={reference}",
    ))
    db.commit()
    return record, True


class CredentialIn(BaseModel):
    issuing_country: str = Field(pattern=r"^[A-Z]{2}$")
    issuing_authority: str = Field(min_length=3, max_length=120)
    verification_reference: str = Field(min_length=6, max_length=100, pattern=REF_PATTERN)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def future_aware(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("Timezone-aware expiration required")
        if not (_now() + timedelta(days=1) <= _utc(value) <= _now() + timedelta(days=366)):
            raise ValueError("Expiration must be between 1 and 366 days from now")
        return value


@router.put("/reviewers/{reviewer_id}/credential")
def locally_attest_reviewer(
    reviewer_id: str,
    body: CredentialIn,
    db: Session = Depends(get_db),
    user: User = Depends(admin),
):
    reviewer = db.scalar(select(User).where(
        User.id == reviewer_id, User.tenant_id == user.tenant_id,
        User.role == "physician", User.active.is_(True),
    ))
    if not reviewer:
        raise HTTPException(404, "Active physician account not found")
    row = db.scalar(select(ReviewerCredential).where(
        ReviewerCredential.tenant_id == user.tenant_id,
        ReviewerCredential.user_id == reviewer.id,
    ).with_for_update())
    if row is None:
        row = ReviewerCredential(
            tenant_id=user.tenant_id, user_id=reviewer.id, checked_by=user.id
        )
        db.add(row)
    row.issuing_country = body.issuing_country
    row.issuing_authority = body.issuing_authority
    row.verification_reference = body.verification_reference
    row.checked_by = user.id
    row.checked_at = _now()
    row.expires_at = _utc(body.expires_at)
    row.status = "locally_attested"
    db.flush()
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event="reviewer_credential_locally_attested",
        entity_type="ReviewerCredential", entity_id=row.id,
    ))
    db.commit()
    return {
        "reviewer_id": reviewer.id, "status": row.status,
        "externally_verified": False, "clinical_release_authorized": False,
    }


class AssignmentIn(BaseModel):
    reviewer_user_id: str


@router.post("/sessions/{session_id}/assignment")
def assign_reviewer(
    session_id: str,
    body: AssignmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(admin),
):
    session = _session(db, user.tenant_id, session_id, lock=True)
    if session.status not in ("awaiting_clinician_review", "handoff_recorded"):
        raise HTTPException(409, "Questionnaire has not been submitted for review")
    reviewer = db.scalar(select(User).where(
        User.id == body.reviewer_user_id,
        User.tenant_id == user.tenant_id, User.role == "physician",
        User.active.is_(True),
    ))
    if not reviewer:
        raise HTTPException(404, "Reviewer not found")
    _credential(db, reviewer)
    existing = db.scalar(select(IntakeReviewerAssignment).where(
        IntakeReviewerAssignment.tenant_id == user.tenant_id,
        IntakeReviewerAssignment.intake_id == session.id,
        IntakeReviewerAssignment.reviewer_user_id == reviewer.id,
    ).with_for_update())
    if existing:
        existing.active = True
        assignment = existing
    else:
        assignment = IntakeReviewerAssignment(
            tenant_id=user.tenant_id, case_id=session.case_id,
            intake_id=session.id, reviewer_user_id=reviewer.id,
            assigned_by=user.id, active=True,
        )
        db.add(assignment)
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event="intake_reviewer_assigned", entity_type="PatientIntake", entity_id=session.id,
    ))
    db.commit()
    return {"intake_id": session.id, "reviewer_id": reviewer.id,
            "assigned": True, "clinical_approval": False}


class RecommendationIn(BaseModel):
    action: Literal[
        "additional_information_requested",
        "external_clinical_assessment_required",
        "nonclinical_handoff_acknowledged",
    ]
    reference: str = Field(min_length=6, max_length=100, pattern=REF_PATTERN)


@router.post("/sessions/{session_id}/recommendation")
def record_reviewer_recommendation(
    session_id: str,
    body: RecommendationIn,
    db: Session = Depends(get_db),
    user: User = Depends(physician),
):
    session = _session(db, user.tenant_id, session_id, lock=True)
    _credential(db, user)
    _assignment(db, session, user)
    if session.status not in ("awaiting_clinician_review", "handoff_recorded"):
        raise HTTPException(409, "This intake cannot receive a reviewer recommendation")
    # This metadata alone NEVER clears an urgent block, approves treatment,
    # or changes the case's readiness for any high-stakes transition.
    row, created = _record(
        db, session, user, "reviewer_" + body.action, body.reference,
    )
    return {"id": row.id, "created": created, "action": body.action,
            "clinical_decision": False, "independent_credential_verified": False,
            "treatment_approved": False}


class EscalationIn(BaseModel):
    action: Literal["urgent_alert_acknowledged", "external_contact_attempt_recorded"]
    reference: str = Field(min_length=6, max_length=100, pattern=REF_PATTERN)


@router.post("/sessions/{session_id}/escalation")
def record_urgent_escalation(
    session_id: str,
    body: EscalationIn,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    session = _session(db, user.tenant_id, session_id, lock=True)
    if session.status != "requires_urgent_human_review":
        raise HTTPException(409, "No active urgent intake alert")
    row, created = _record(db, session, user, body.action, body.reference)
    return {"id": row.id, "created": created,
            "urgent_alert_active": True, "contact_success_confirmed": False,
            "automated_clearance": False}


@router.get("/sessions/{session_id}/events")
def review_event_history(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(roles("admin", "operator", "physician")),
):
    session = _session(db, user.tenant_id, session_id)
    if user.role == "physician":
        _credential(db, user)
        _assignment(db, session, user)
    rows = db.scalars(select(IntakeReviewRecord).where(
        IntakeReviewRecord.tenant_id == user.tenant_id,
        IntakeReviewRecord.intake_id == session.id,
        IntakeReviewRecord.case_id == session.case_id,
    ).order_by(IntakeReviewRecord.created_at, IntakeReviewRecord.id).limit(100)).all()
    return {
        "records": [
            {"id": r.id, "action": r.action, "created_at": r.created_at,
             "external_confirmation": False} for r in rows
        ],
        "urgent_alert_active": session.status == "requires_urgent_human_review",
        "clinical_approval": False,
    }


@router.get("/my-assignments")
def my_review_assignments(
    db: Session = Depends(get_db),
    user: User = Depends(physician),
):
    _credential(db, user)
    assignments = db.scalars(select(IntakeReviewerAssignment).where(
        IntakeReviewerAssignment.tenant_id == user.tenant_id,
        IntakeReviewerAssignment.reviewer_user_id == user.id,
        IntakeReviewerAssignment.active.is_(True),
    ).order_by(IntakeReviewerAssignment.created_at.desc()).limit(100)).all()
    results = []
    for row in assignments:
        intake = db.scalar(select(PatientIntake).where(
            PatientIntake.id == row.intake_id,
            PatientIntake.tenant_id == user.tenant_id,
            PatientIntake.case_id == row.case_id,
        ))
        if not intake or latest_intake(db, user.tenant_id, row.case_id).id != intake.id:
            continue
        if intake.status not in ("awaiting_clinician_review", "handoff_recorded"):
            continue
        case = db.scalar(select(Case).where(
            Case.id == row.case_id, Case.tenant_id == user.tenant_id
        ))
        if case and active_consent(db, user.tenant_id, case.patient_id, "intake"):
            results.append({
                "case_id": row.case_id, "session_id": row.intake_id,
                "status": intake.status, "language": intake.language,
                "clinical_authorization": False,
            })
    return {"items": results, "raw_medical_answers_included": False}


@router.get("/escalation-policy")
def escalation_policy(user: User = Depends(staff)):
    from .intake import EMERGENCY_RESPONSE
    return {
        "signal_type": "precautionary_keyword_only",
        "clinical_triage_validated": False,
        "safe_to_ignore_nonmatching_messages": False,
        "automatic_alert_clearance": False,
        "automated_emergency_contact": False,
        "country_specific_contact_numbers_verified": False,
        "instructions": EMERGENCY_RESPONSE,
        "required_next_step": "Human coordinator requests local emergency services outside this alpha service",
    }
