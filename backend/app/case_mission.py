"""Case-centric international patient coordination mission (development-only).

No clinical decisions, provider bookings, border-entry confirmations or payments are
made here. Milestones reflect recorded and human-reviewed evidence, not verification
against independent external systems. All reads are explicitly tenant scoped.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    Appointment, Case, Consent, Conversation, Document, Physician,
    Quote, Referral, TravelRequest, User,
)
from .enterprise_models import CaseTimeline, Operation, PatientIntake
from .security import roles

router = APIRouter(prefix="/api/v1/cases", tags=["case mission"])
staff = roles("admin", "operator")

TRAVEL_KINDS = frozenset({
    "visa", "hotel", "transport", "airport_pickup",
    "interpreter", "hospital_admission", "home_visit",
})
# This is a conservative set of administrative state gates. Treatment requires
# additional external/clinical approval before a real production release.
REQUIREMENTS = {
    "review_pending": ("intake_submitted", "emergency_clear"),
    "provider_review": ("intake_submitted", "emergency_clear"),
    "quote_pending": ("referral_approved", "emergency_clear"),
    "quote_sent": ("quote_approved", "emergency_clear"),
    "confirmed": ("quote_approved", "appointment_confirmed", "emergency_clear"),
    "travel_planning": ("appointment_confirmed", "emergency_clear"),
    "arrived": ("travel_resolved", "emergency_clear"),
    "in_treatment": ("appointment_confirmed", "emergency_clear"),
    "follow_up": ("emergency_clear",),
    "closed": ("followup_recorded", "emergency_clear"),
}
SUPERVISOR_STAGES = frozenset({"confirmed", "arrived", "in_treatment", "follow_up", "closed"})
ATTESTED_STAGES = SUPERVISOR_STAGES


def _rows(db: Session, model, tenant_id: str, *predicates):
    return list(db.scalars(select(model).where(model.tenant_id == tenant_id, *predicates)).all())


def _consented(db: Session, tenant_id: str, patient_id: str, purpose: str) -> bool:
    last = db.scalar(
        select(Consent)
        .where(
            Consent.tenant_id == tenant_id,
            Consent.patient_id == patient_id,
            Consent.purpose == purpose,
        )
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .limit(1)
    )
    return bool(last and last.accepted)


def mission_evidence(db: Session, case: Case) -> dict:
    """Read-only evidence check; never trusts a client-provided tenant ID."""
    t = case.tenant_id
    consent = _consented(db, t, case.patient_id, "intake")
    communication = _consented(db, t, case.patient_id, "communication")
    intakes = _rows(db, PatientIntake, t, PatientIntake.case_id == case.id)
    emergency = any(x.status == "requires_urgent_human_review" for x in intakes)
    intake_submitted = consent and any(
        x.status == "awaiting_clinician_review" for x in intakes
    )
    referrals = _rows(db, Referral, t, Referral.case_id == case.id)
    providers = {
        x.id: x for x in _rows(db, Physician, t)
        if x.credential_status == "verified"
    }
    reviewed_referrals = {
        r.physician_id for r in referrals
        if r.status == "approved" and r.physician_id in providers
    }
    quotes = _rows(db, Quote, t, Quote.case_id == case.id)
    approved_quotes = [
        x for x in quotes if x.status == "approved" and x.approved_by
    ]
    appts = _rows(db, Appointment, t, Appointment.case_id == case.id)
    confirmed_appts = [
        x for x in appts if x.status == "confirmed"
        and x.confirmation_reference
        and x.physician_id in reviewed_referrals
    ]
    travel = _rows(db, TravelRequest, t, TravelRequest.case_id == case.id)
    ops = _rows(db, Operation, t, Operation.case_id == case.id)
    travel_ops = [x for x in ops if x.kind in TRAVEL_KINDS]
    unresolved_travel = any(
        x.status not in ("confirmed", "cancelled") or
        (x.status == "confirmed" and not x.external_reference)
        for x in travel
    ) or any(
        x.status not in ("confirmed", "completed", "cancelled") or
        (x.status in ("confirmed", "completed") and
         (not x.confirmed_reference or not x.approved_by))
        for x in travel_ops
    )
    followups = [
        x for x in ops if x.kind == "followup"
        and x.status in ("confirmed", "completed")
        and x.confirmed_reference and x.approved_by
    ]
    conversations = _rows(
        db, Conversation, t, Conversation.patient_id == case.patient_id
    )
    docs = _rows(db, Document, t, Document.case_id == case.id)
    conditions = {
        "intake_consent": consent,
        "communication_consent": communication,
        "intake_submitted": intake_submitted,
        "emergency_clear": not emergency,
        "referral_approved": bool(reviewed_referrals) and not emergency,
        "quote_approved": bool(approved_quotes),
        "appointment_confirmed": bool(confirmed_appts) and not emergency,
        "travel_resolved": not unresolved_travel,
        "followup_recorded": bool(followups),
    }
    return {
        "case_id": case.id,
        "status": case.status,
        "conditions": conditions,
        "signals": {
            "has_staff_conversation": bool(conversations) and communication,
            "human_handoff": any(x.human_handoff for x in conversations),
            "documents_recorded": len(docs),
            "travel_services_requested": len(travel) + len(travel_ops),
            "travel_services_unresolved": unresolved_travel,
            "urgent_intake_detected": emergency,
        },
        "required_for_status": {
            stage: list(requirements) for stage, requirements in REQUIREMENTS.items()
        },
        "note": (
            "Coordination status from recorded evidence only; not an independent "
            "clinical decision, arrival, booking, payment or provider confirmation."
        ),
    }


def check_mission_transition(db: Session, case: Case, target: str, role: str, reference: str | None):
    if target in SUPERVISOR_STAGES and role != "admin":
        raise HTTPException(403, "Supervisor approval required for this milestone")
    if target in ATTESTED_STAGES and not reference:
        raise HTTPException(422, "Human evidence reference required for this milestone")
    conditions = mission_evidence(db, case)["conditions"]
    missing = [
        key for key in REQUIREMENTS.get(target, ())
        if not conditions[key]
    ]
    if missing:
        raise HTTPException(
            409, {"code": "MISSION_PREREQUISITES_MISSING", "missing": missing}
        )


@router.get("/{case_id}/mission")
def read_case_mission(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    case = db.scalar(
        select(Case).where(Case.id == case_id, Case.tenant_id == user.tenant_id)
    )
    if case is None:
        raise HTTPException(404, "Record not found")
    return mission_evidence(db, case)


@router.get("/{case_id}/mission/history")
def read_case_mission_history(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    case = db.scalar(
        select(Case.id).where(
            Case.id == case_id, Case.tenant_id == user.tenant_id
        )
    )
    if not case:
        raise HTTPException(404, "Record not found")
    timeline = db.scalars(
        select(CaseTimeline).where(
            CaseTimeline.tenant_id == user.tenant_id,
            CaseTimeline.case_id == case_id,
            CaseTimeline.event == "case_status_transition",
        ).order_by(CaseTimeline.created_at, CaseTimeline.id)
    ).all()
    return [
        {
            "id": x.id,
            "actor_id": x.actor_id,
            "created_at": x.created_at,
            "current_status": x.details.split(";")[0].split("->")[-1],
            "evidence_reference": x.details.partition(";evidence=")[-1],
        }
        for x in timeline
    ]
