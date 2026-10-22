"""Consent-aware WhatsApp-first and secure-portal fallback coordination.

This gateway creates only internal administrative tasks. It never transmits a
message, returns a patient portal bearer token, links a Telegram identity to a
patient, or certifies an external channel as live.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Audit, Case, Patient, Task, User
from .security import roles
from .safety_rules import active_consent, INVITATION_TASK_TITLE
from .whatsapp import enabled as whatsapp_configured
from .telegram import enabled as telegram_configured
from .delivery import enabled as outbound_configured

router = APIRouter(prefix="/api/v1/channels", tags=["channel orchestration"])
staff = roles("admin", "operator")
_INVITATION_TASK = INVITATION_TASK_TITLE


def _record(db: Session, case: Case, actor: User):
    db.add(Audit(
        tenant_id=actor.tenant_id,
        user_id=actor.id,
        event="secure_portal_handoff_requested",
        entity_type="Case",
        entity_id=case.id,
    ))


@router.get("/readiness")
def channel_readiness(user: User = Depends(staff)):
    # Configured != live or authorized to process actual medical information.
    return {
        "primary": "whatsapp",
        "channels": {
            "whatsapp": {
                "configured": bool(whatsapp_configured()),
                "outbound_configured": bool(outbound_configured()),
                "live_verified": False,
                "patient_data_approved": False,
                "capability": "human_review_inbound_and_generic_approved_templates",
            },
            "telegram": {
                "configured": bool(telegram_configured()),
                "live_verified": False,
                "patient_data_approved": False,
                "capability": "public_onboarding_only",
            },
            "secure_portal": {
                "configured": True,
                "live_verified": False,
                "patient_data_approved": False,
                "capability": "revocable_invitation_pending_identity_assurance",
            },
        },
        "fallback": "secure_portal",
        "automatic_channel_fallback": False,
        "automatic_external_sends": False,
        "production_ready": False,
    }


@router.get("/patients/{patient_id}/options")
def patient_channel_options(
    patient_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    patient = db.scalar(select(Patient).where(
        Patient.id == patient_id, Patient.tenant_id == user.tenant_id,
    ))
    if patient is None:
        raise HTTPException(404, "Patient not found")
    consent = active_consent(db, user.tenant_id, patient.id, "communication")
    # Do not expose a phone, Telegram identity or patient access token.
    return {
        "communication_consent": consent,
        "primary": "whatsapp",
        "whatsapp_outbound_configured": bool(consent and whatsapp_configured()
                                             and outbound_configured()),
        "whatsapp_usable": False,  # Cannot establish real delivery eligibility from env flags.
        "secure_portal_invitation_permitted": consent,
        "telegram_patient_routing_supported": False,
        "automatic_message_sent": False,
        "note": "Provider readiness is configured-only; not a live account check.",
    }


@router.post("/cases/{case_id}/secure-portal-handoff", status_code=201)
def secure_portal_handoff(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    case = db.scalar(select(Case).where(
        Case.id == case_id, Case.tenant_id == user.tenant_id,
    ).with_for_update())
    if case is None:
        raise HTTPException(404, "Case not found")
    if not active_consent(db, user.tenant_id, case.patient_id, "communication"):
        raise HTTPException(409, "Active communication consent required")

    existing = db.scalar(select(Task).where(
        Task.tenant_id == user.tenant_id,
        Task.case_id == case.id,
        Task.title == _INVITATION_TASK,
        Task.status == "open",
    ).order_by(Task.created_at.desc(), Task.id.desc()).limit(1))
    if existing:
        return {
            "task_id": existing.id, "status": "awaiting_human_invitation",
            "deduplicated": True, "sent": False,
            "portal_token_issued": False,
        }

    task = Task(
        tenant_id=user.tenant_id, case_id=case.id,
        title=_INVITATION_TASK, status="open",
    )
    db.add(task)
    db.flush()
    _record(db, case, user)
    db.commit()
    return {
        "task_id": task.id, "status": "awaiting_human_invitation",
        "deduplicated": False, "sent": False,
        "portal_token_issued": False,
        "next_staff_action": "/api/v1/portal/invites/" + case.patient_id,
        "warning": "Verify identity and authorized private delivery before issuing any link.",
    }
