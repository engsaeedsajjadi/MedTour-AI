"""Non-negotiable safety boundaries for MedTour's development build.

No environment flag, demo config, or unreviewed document may certify an alpha
health-coordination application for real patient/medical-data processing.
"""
from __future__ import annotations

import os
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Case, Consent, Conversation, Task, Document
from .enterprise_models import OutboundMessage, PortalAccess, TranslationDraft, CRMFollowUp


SAFETY_POLICY_VERSION = "section-02-2026-10-22"
INVITATION_TASK_TITLE = "Prepare secure portal invitation via an approved private channel"
CONSENT_PURPOSES = frozenset({
    "intake", "medical_documents", "communication", "ai_processing"
})


def assert_safe_runtime(environment: str | None = None) -> None:
    """Fail closed until production RLS, identity, clinical/privacy review exist.

    Deliberately does not accept a bypass environment variable. A future
    independently reviewed release must replace this gate with evidence-based
    production authorization, including migrations and provider sign-off.
    """
    mode = (environment if environment is not None else
            os.getenv("APP_ENV", "development")).strip().lower()
    if mode == "production":
        raise RuntimeError(
            "MedTour 0.5.0-alpha is NOT authorized for production PHI. "
            "Complete tenant RLS migration, identity assurance, independent "
            "clinical/privacy/security reviews and provider approvals first."
        )


def active_consent(db: Session, tenant_id: str, patient_id: str, purpose: str) -> bool:
    if purpose not in CONSENT_PURPOSES:
        return False
    last = db.scalar(
        select(Consent).where(
            Consent.tenant_id == tenant_id,
            Consent.patient_id == patient_id,
            Consent.purpose == purpose,
        ).order_by(Consent.created_at.desc(), Consent.id.desc()).limit(1)
    )
    return bool(last and last.accepted)


def revoke_patient_access(db: Session, tenant_id: str, patient_id: str, purpose: str) -> dict:
    """Revoke in the SAME DB transaction as the consent withdrawal.

    Applies to both staff-recorded and patient-link withdrawals. Pending AI
    translation buffers are scrubbed when communication/AI consent is withdrawn;
    already delivered messages need separately governed retention/erasure.
    """
    grants = db.scalars(select(PortalAccess).where(
        PortalAccess.tenant_id == tenant_id,
        PortalAccess.patient_id == patient_id,
        PortalAccess.revoked.is_(False),
    )).all()
    for grant in grants:
        grant.revoked = True

    outbox = db.scalars(select(OutboundMessage).where(
        OutboundMessage.tenant_id == tenant_id,
        OutboundMessage.patient_id == patient_id,
        OutboundMessage.status.in_(("pending_approval", "approved")),
    )).all()
    for item in outbox:
        item.status = "blocked"

    # Withdrawing communication permission blocks pending CRM outreach tasks.
    # This is metadata-only; no external message is dispatched here.
    blocked_followups = []
    if purpose == "communication":
        blocked_followups = db.scalars(select(CRMFollowUp).where(
            CRMFollowUp.tenant_id == tenant_id,
            CRMFollowUp.patient_id == patient_id,
            CRMFollowUp.status == "open",
        )).all()
        for task in blocked_followups:
            task.status = "blocked"

    # An unfulfilled portal-invitation handoff is cancelled on withdrawal.
    if purpose == "communication":
        case_ids = select(Case.id).where(
            Case.tenant_id == tenant_id, Case.patient_id == patient_id,
        )
        handoffs = db.scalars(select(Task).where(
            Task.tenant_id == tenant_id,
            Task.case_id.in_(case_ids),
            Task.title == INVITATION_TASK_TITLE,
            Task.status == "open",
        )).all()
        for task in handoffs:
            task.status = "cancelled"

    revoked_documents = []
    if purpose == "medical_documents":
        revoked_documents = db.scalars(select(Document).where(
            Document.tenant_id == tenant_id,
            Document.patient_id == patient_id,
            Document.status.in_(("encrypted_dev_unscanned", "scanned_private_s3")),
        )).all()
        for document in revoked_documents:
            # Never make an earlier document accessible again after re-consent.
            # Physical erasure requires separately reviewed retention policy.
            document.status = "access_revoked"

    drafts = []
    if purpose in ("communication", "ai_processing"):
        conversations = select(Conversation.id).where(
            Conversation.tenant_id == tenant_id,
            Conversation.patient_id == patient_id,
        )
        drafts = db.scalars(select(TranslationDraft).where(
            TranslationDraft.tenant_id == tenant_id,
            TranslationDraft.conversation_id.in_(conversations),
            TranslationDraft.status == "pending_review",
        )).all()
        for row in drafts:
            row.status = "blocked"
            row.source_text = ""
            row.draft_text = ""
    return {
        "portal_grants_revoked": len(grants),
        "outbound_blocked": len(outbox),
        "ai_translation_drafts_blocked": len(drafts),
        "documents_access_revoked": len(revoked_documents),
        "crm_followups_blocked": len(blocked_followups),
    }


def public_safety_contract() -> dict:
    """Explicitly prevent UI / API clients from inferring production approval."""
    return {
        "policy_version": SAFETY_POLICY_VERSION,
        "development_build": True,
        "production_ready": False,
        "real_patient_data_allowed": False,
        "automatic_diagnosis_allowed": False,
        "automatic_treatment_or_visa_approval_allowed": False,
        "real_provider_booking_verified": False,
        "clinical_decisions_require_qualified_human": True,
        "external_confirmations_require_independent_evidence": True,
        "patient_identity_assurance_complete": False,
        "runtime_row_level_security_complete": False,
    }
