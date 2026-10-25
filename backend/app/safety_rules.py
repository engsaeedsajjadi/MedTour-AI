"""Non-negotiable safety boundaries for MedTour's development build.

No environment flag, demo config, or unreviewed document may certify an alpha
health-coordination application for real patient/medical-data processing.
"""
from __future__ import annotations

import os
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Case, Consent, Conversation, Task, Document, Patient
from .enterprise_models import OutboundMessage, PortalAccess, TranslationDraft, CRMFollowUp, HospitalCoordination, ProviderMatch, AppointmentSlot, MedicalVisa, AccommodationStay, TravelAssignment, AgentReferralIntent, LeadSource


SAFETY_POLICY_VERSION = "section-02-2026-10-22"
INVITATION_TASK_TITLE = "Prepare secure portal invitation via an approved private channel"
CONSENT_PURPOSES = frozenset({
    "intake", "medical_documents", "communication", "ai_processing",
    "hospital_coordination", "visa_coordination", "accommodation_coordination", "transport_coordination", "interpreter_coordination", "agent_referral"
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
    # Serialize consent withdrawal with consent-sensitive agent attribution.
    # The matching flow also locks this patient row before checking consent.
    db.scalar(select(Patient.id).where(
        Patient.tenant_id == tenant_id,
        Patient.id == patient_id,
    ).with_for_update())

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

    blocked_appointments = []
    if purpose == "intake":
        blocked_appointments = db.scalars(select(AppointmentSlot).where(
            AppointmentSlot.tenant_id == tenant_id,
            AppointmentSlot.patient_id == patient_id,
            AppointmentSlot.status.in_(("requested", "internally_confirmed")),
        )).all()
        for item in blocked_appointments:
            item.status = "blocked"

    blocked_provider_matches = []
    if purpose == "intake":
        blocked_provider_matches = db.scalars(select(ProviderMatch).where(
            ProviderMatch.tenant_id == tenant_id,
            ProviderMatch.patient_id == patient_id,
            ProviderMatch.status.in_(("pending_human_review", "administratively_shortlisted")),
        )).all()
        for row in blocked_provider_matches:
            row.status = "blocked"

    blocked_hospital_requests = []
    if purpose in ("intake", "hospital_coordination"):
        blocked_hospital_requests = db.scalars(select(HospitalCoordination).where(
            HospitalCoordination.tenant_id == tenant_id,
            HospitalCoordination.patient_id == patient_id,
            HospitalCoordination.status.in_(("requested", "received")),
        )).all()
        for request in blocked_hospital_requests:
            request.status = "blocked"

    blocked_visas = []
    if purpose in ("intake", "medical_documents", "visa_coordination"):
        blocked_visas = db.scalars(select(MedicalVisa).where(
            MedicalVisa.tenant_id == tenant_id,
            MedicalVisa.patient_id == patient_id,
            MedicalVisa.status.in_(("requested", "in_review",
                                    "ready_for_manual_submission", "submission_reported")),
        )).all()
        for request in blocked_visas:
            # Never reactivate this record after later re-consent.
            # An already reported government submission needs separate manual follow-up.
            request.status = "blocked"

    blocked_stays = []
    if purpose in ("intake", "accommodation_coordination"):
        blocked_stays = db.scalars(select(AccommodationStay).where(
            AccommodationStay.tenant_id == tenant_id,
            AccommodationStay.patient_id == patient_id,
            AccommodationStay.status.in_(("requested", "internally_held",
                "external_request_reported", "external_confirmation_reported")),
        )).all()
        for request in blocked_stays:
            # Old stay does not reactivate after new consent.
            # Any provider-facing cancellation is a separate human task.
            request.status = "blocked"

    blocked_assignments = []
    if purpose in ("intake", "transport_coordination", "interpreter_coordination"):
        predicates = [
            TravelAssignment.tenant_id == tenant_id,
            TravelAssignment.patient_id == patient_id,
            TravelAssignment.status.in_(("requested","internally_allocated",
                                          "provider_contact_reported","provider_ack_reported"))]
        if purpose == "transport_coordination":
            predicates.append(TravelAssignment.kind != "interpreter_session")
        if purpose == "interpreter_coordination":
            predicates.append(TravelAssignment.kind == "interpreter_session")
        blocked_assignments = db.scalars(select(TravelAssignment).where(*predicates)).all()
        for assignment in blocked_assignments:
            # Remains blocked even after renewed consent, and allocated resources
            # remain occupied until separately reconciled with the external provider.
            assignment.status = "blocked"

    blocked_agent_referrals = []
    if purpose in ("intake", "agent_referral"):
        blocked_agent_referrals = db.scalars(select(AgentReferralIntent).where(
            AgentReferralIntent.tenant_id == tenant_id,
            AgentReferralIntent.patient_id == patient_id,
            AgentReferralIntent.status == "attributed",
        )).all()
        for intent in blocked_agent_referrals:
            # Old attribution never reactivates on future reconsent.
            intent.status = "blocked"

    unlinked_agent_leads = []
    if purpose in ("intake", "agent_referral"):
        unlinked_agent_leads = db.scalars(select(LeadSource).where(
            LeadSource.tenant_id == tenant_id,
            LeadSource.patient_id == patient_id,
            LeadSource.source == "agent_portal",
            LeadSource.agent_id.is_not(None),
        )).all()
        for lead in unlinked_agent_leads:
            # Historical audit remains, but no active agent attribution survives.
            lead.agent_id = None
            lead.source = "agent_referral_revoked"

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
        "hospital_requests_blocked": len(blocked_hospital_requests),
        "provider_matches_blocked": len(blocked_provider_matches),
        "appointment_slots_blocked": len(blocked_appointments),
        "visa_records_blocked": len(blocked_visas),
        "accommodation_stays_blocked": len(blocked_stays),
        "travel_assignments_blocked": len(blocked_assignments),
        "agent_referrals_blocked": len(blocked_agent_referrals),
        "agent_leads_unlinked": len(unlinked_agent_leads),
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
