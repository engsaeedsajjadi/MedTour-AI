"""Additional operational entities. These are coordination records, NOT clinical orders."""
from __future__ import annotations
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, BigInteger, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import TenantEntity, uid, utcnow

class Operation(TenantEntity,Base):
    __tablename__='operations'
    kind:Mapped[str]=mapped_column(String(40),nullable=False,index=True)
    case_id:Mapped[str|None]=mapped_column(ForeignKey('cases.id'),nullable=True,index=True)
    patient_id:Mapped[str|None]=mapped_column(ForeignKey('patients.id'),nullable=True,index=True)
    title:Mapped[str]=mapped_column(String(250),nullable=False)
    status:Mapped[str]=mapped_column(String(32),default='requested',nullable=False)
    metadata_json:Mapped[str]=mapped_column(Text,default='{}',nullable=False)
    assigned_to:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    confirmed_reference:Mapped[str|None]=mapped_column(String(200),nullable=True)
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    __table_args__=(Index('idx_operations_tenant_kind_status','tenant_id','kind','status'),)

class OperationEvent(TenantEntity,Base):
    __tablename__='operation_events'
    operation_id:Mapped[str]=mapped_column(ForeignKey('operations.id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    old_status:Mapped[str]=mapped_column(String(32))
    new_status:Mapped[str]=mapped_column(String(32))
    note:Mapped[str]=mapped_column(String(500),default='')

class ServicePrice(TenantEntity,Base):
    __tablename__='service_prices'
    service_code:Mapped[str]=mapped_column(String(90))
    label:Mapped[str]=mapped_column(String(200))
    currency:Mapped[str]=mapped_column(String(3))
    amount_minor:Mapped[int]=mapped_column(BigInteger)
    source:Mapped[str]=mapped_column(String(180))
    verified_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    valid_until:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    active:Mapped[bool]=mapped_column(Boolean,default=True)

class QuoteItem(TenantEntity,Base):
    __tablename__='quote_items'
    quote_id:Mapped[str]=mapped_column(ForeignKey('quotes.id'),index=True)
    label:Mapped[str]=mapped_column(String(200))
    units:Mapped[int]=mapped_column(Integer,default=1)
    unit_amount_minor:Mapped[int]=mapped_column(BigInteger)
    provenance:Mapped[str]=mapped_column(String(300))

class WorkflowEvent(TenantEntity,Base):
    __tablename__='workflow_events'
    workflow:Mapped[str]=mapped_column(String(100),index=True)
    resource_id:Mapped[str]=mapped_column(String(36),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(70))
    detail:Mapped[str]=mapped_column(String(700),default='')

class PortalAccess(TenantEntity,Base):
    __tablename__='portal_access'
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),index=True)
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
    issued_by:Mapped[str]=mapped_column(ForeignKey('users.id'))

# Section 21: invitation + independent code entry before minting patient access.
# Staff-only demo code handoff is NOT independently verified patient identity.
class PortalLoginChallenge(TenantEntity, Base):
    __tablename__ = "portal_login_challenges"
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    invitation_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    __table_args__ = (Index("idx_portal_login_patient", "tenant_id", "patient_id", "expires_at"),)

class ContentPage(TenantEntity,Base):
    __tablename__='content_pages'
    slug:Mapped[str]=mapped_column(String(150))
    locale:Mapped[str]=mapped_column(String(10))
    title:Mapped[str]=mapped_column(String(250))
    body:Mapped[str]=mapped_column(Text,default='')
    status:Mapped[str]=mapped_column(String(24),default='draft')
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    published_version_no:Mapped[int|None]=mapped_column(Integer,nullable=True)
    __table_args__=(UniqueConstraint('tenant_id','slug','locale'),)

class CmsVersion(TenantEntity,Base):
    __tablename__='cms_versions'
    page_id:Mapped[str]=mapped_column(ForeignKey('content_pages.id'),nullable=False)
    version_no:Mapped[int]=mapped_column(Integer,nullable=False)
    title:Mapped[str]=mapped_column(String(250),nullable=False)
    body:Mapped[str]=mapped_column(Text,nullable=False)
    content_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    author_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    reason:Mapped[str]=mapped_column(String(200),nullable=False)
    status:Mapped[str]=mapped_column(String(30),nullable=False,default='draft')
    __table_args__=(UniqueConstraint('tenant_id','page_id','version_no'),
        Index('ix_cms_versions_page','tenant_id','page_id','version_no'),)

class CmsReview(TenantEntity,Base):
    __tablename__='cms_reviews'
    version_id:Mapped[str]=mapped_column(ForeignKey('cms_versions.id'),nullable=False)
    stage:Mapped[str]=mapped_column(String(30),nullable=False)
    decision:Mapped[str]=mapped_column(String(30),nullable=False)
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    evidence_reference:Mapped[str]=mapped_column(String(100),nullable=False)
    __table_args__=(UniqueConstraint('tenant_id','version_id','stage'),
        Index('ix_cms_reviews_version','tenant_id','version_id'),)

class CmsWorkflowEvent(TenantEntity,Base):
    __tablename__='cms_workflow_events'
    page_id:Mapped[str]=mapped_column(ForeignKey('content_pages.id'),nullable=False)
    version_id:Mapped[str|None]=mapped_column(ForeignKey('cms_versions.id'),nullable=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    action:Mapped[str]=mapped_column(String(55),nullable=False)
    reference:Mapped[str]=mapped_column(String(100),nullable=False,default='')
    __table_args__=(Index('ix_cms_workflow_events_page','tenant_id','page_id','created_at'),)

class TenantSetting(TenantEntity,Base):
    __tablename__='tenant_settings'
    key:Mapped[str]=mapped_column(String(100))
    value_json:Mapped[str]=mapped_column(Text,default='{}')
    __table_args__=(UniqueConstraint('tenant_id','key'),)

class KnowledgeArticle(TenantEntity,Base):
    __tablename__='knowledge_articles'
    locale:Mapped[str]=mapped_column(String(10))
    title:Mapped[str]=mapped_column(String(240))
    body:Mapped[str]=mapped_column(Text)
    approved:Mapped[bool]=mapped_column(Boolean,default=False)
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)

class AILog(TenantEntity,Base):
    __tablename__='ai_logs'
    case_id:Mapped[str|None]=mapped_column(ForeignKey('cases.id'),nullable=True)
    provider:Mapped[str]=mapped_column(String(90))
    purpose:Mapped[str]=mapped_column(String(90))
    outcome:Mapped[str]=mapped_column(String(32))
    tokens:Mapped[int]=mapped_column(Integer,default=0)
    latency_ms:Mapped[int]=mapped_column(Integer,default=0)
    # Never persist prompts, PHI, raw responses, or access tokens here.

class AIAgentPolicy(TenantEntity,Base):
    __tablename__="ai_agent_policies"
    agent_key:Mapped[str]=mapped_column(String(60),nullable=False)
    enabled:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    provider_mode:Mapped[str]=mapped_column(String(25),nullable=False,default="deterministic_demo")
    daily_run_limit:Mapped[int]=mapped_column(Integer,nullable=False,default=20)
    updated_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    __table_args__=(UniqueConstraint("tenant_id","agent_key"),)

class AIOrchestrationRun(TenantEntity,Base):
    __tablename__="ai_orchestration_runs"
    request_key:Mapped[str]=mapped_column(String(100),nullable=False)
    agent_key:Mapped[str]=mapped_column(String(60),nullable=False)
    workflow:Mapped[str]=mapped_column(String(60),nullable=False)
    locale:Mapped[str]=mapped_column(String(10),nullable=False)
    input_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    status:Mapped[str]=mapped_column(String(40),nullable=False,default="pending_human_review")
    mode:Mapped[str]=mapped_column(String(25),nullable=False,default="deterministic_demo")
    result_text:Mapped[str]=mapped_column(Text,nullable=False)
    knowledge_ids_json:Mapped[str]=mapped_column(Text,nullable=False,default="[]")
    authored_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    reviewer_id:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    decision_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","request_key"),
        Index("ix_ai_orchestration_tenant_state","tenant_id","status","created_at"),)

class AIOrchestrationEvent(TenantEntity,Base):
    __tablename__="ai_orchestration_events"
    run_id:Mapped[str]=mapped_column(ForeignKey("ai_orchestration_runs.id"),nullable=False)
    actor_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    action:Mapped[str]=mapped_column(String(80),nullable=False)
    detail_code:Mapped[str]=mapped_column(String(80),nullable=False)
    __table_args__=(Index("ix_ai_orchestration_events_run","tenant_id","run_id","created_at"),)

class StaffMFA(TenantEntity,Base):
    __tablename__="staff_mfa"
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    secret_encrypted:Mapped[str]=mapped_column(Text,nullable=False)
    enabled:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    last_counter:Mapped[int]=mapped_column(BigInteger,default=-1,nullable=False)
    __table_args__=(UniqueConstraint("tenant_id","user_id"),)

class DoctorCaseGrant(TenantEntity,Base):
    __tablename__="doctor_case_grants"
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    case_id:Mapped[str]=mapped_column(ForeignKey("cases.id"),nullable=False)
    granted_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","user_id","case_id"),)

class VoiceSampleJob(TenantEntity,Base):
    """Only hashes and review metadata. No raw audio or transcript content."""
    __tablename__="voice_sample_jobs"
    request_key:Mapped[str]=mapped_column(String(100),nullable=False)
    kind:Mapped[str]=mapped_column(String(12),nullable=False)
    locale:Mapped[str]=mapped_column(String(10),nullable=False)
    source_format:Mapped[str]=mapped_column(String(16),nullable=False)
    audio_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    transcript_sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)
    duration_ms:Mapped[int]=mapped_column(Integer,nullable=False)
    status:Mapped[str]=mapped_column(String(32),nullable=False)
    author_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    reviewer_id:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    review_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","request_key"),
        Index("ix_voice_samples_tenant_state","tenant_id","status","created_at"),)

class MessageEvent(TenantEntity,Base):
    __tablename__='message_events'
    event_id:Mapped[str]=mapped_column(String(150))
    channel:Mapped[str]=mapped_column(String(30))
    status:Mapped[str]=mapped_column(String(60),default='received')
    provider_account_id:Mapped[str]=mapped_column(String(120))
    payload_hash:Mapped[str]=mapped_column(String(64))
    # No unconsented inbound medical content stored.
    __table_args__=(UniqueConstraint('tenant_id','channel','event_id'),)

class PatientIntake(TenantEntity,Base):
    __tablename__='patient_intakes'
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'),index=True)
    language:Mapped[str]=mapped_column(String(10))
    stage:Mapped[int]=mapped_column(Integer,default=0)
    answers_json:Mapped[str]=mapped_column(Text,default='{}')
    status:Mapped[str]=mapped_column(String(35),default='in_progress')

class Notification(TenantEntity,Base):
    __tablename__='notifications'
    recipient_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    title:Mapped[str]=mapped_column(String(200))
    body:Mapped[str]=mapped_column(String(500),default='')
    read_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class AgentProfile(TenantEntity,Base):
    __tablename__='agents'
    name:Mapped[str]=mapped_column(String(200))
    country:Mapped[str]=mapped_column(String(100))
    referral_code:Mapped[str]=mapped_column(String(50))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(UniqueConstraint('tenant_id','referral_code'),)

class LeadSource(TenantEntity,Base):
    __tablename__='lead_sources'
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'))
    agent_id:Mapped[str|None]=mapped_column(ForeignKey('agents.id'),nullable=True)
    source:Mapped[str]=mapped_column(String(80),default='direct')
    campaign:Mapped[str]=mapped_column(String(120),default='')

class MoneyEntry(TenantEntity,Base):
    __tablename__='money_entries'
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'))
    entry_type:Mapped[str]=mapped_column(String(40))
    currency:Mapped[str]=mapped_column(String(3))
    amount_minor:Mapped[int]=mapped_column(BigInteger)
    source_reference:Mapped[str]=mapped_column(String(200))
    verified_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('tenant_id','entry_type','source_reference'),)

class CaseTimeline(TenantEntity,Base):
    __tablename__='case_timeline'
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    event:Mapped[str]=mapped_column(String(120))
    details:Mapped[str]=mapped_column(String(500),default='')

class RefreshSession(TenantEntity,Base):
    __tablename__='refresh_sessions'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    refresh_hash:Mapped[str]=mapped_column(String(64),unique=True,index=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    last_rotated_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    family_id:Mapped[str]=mapped_column(String(36),index=True)

class RevokedAccess(TenantEntity,Base):
    __tablename__='revoked_access'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    jti_hash:Mapped[str]=mapped_column(String(64),unique=True,index=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))


class TranslationDraft(TenantEntity,Base):
    __tablename__='translation_drafts'
    conversation_id:Mapped[str]=mapped_column(ForeignKey('conversations.id'),index=True)
    source_language:Mapped[str]=mapped_column(String(10))
    target_language:Mapped[str]=mapped_column(String(10))
    source_text:Mapped[str]=mapped_column(Text)
    draft_text:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(24),default='pending_review')
    reviewer_id:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class OutboundMessage(TenantEntity,Base):
    __tablename__='outbound_messages'
    conversation_id:Mapped[str]=mapped_column(ForeignKey('conversations.id'),index=True)
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),index=True)
    idempotency_key:Mapped[str]=mapped_column(String(100))
    destination_channel:Mapped[str]=mapped_column(String(30),default='whatsapp')
    template_name:Mapped[str]=mapped_column(String(100))
    locale:Mapped[str]=mapped_column(String(10))
    status:Mapped[str]=mapped_column(String(35),default='pending_approval')
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    provider_message_id:Mapped[str|None]=mapped_column(String(160),nullable=True)
    attempt_count:Mapped[int]=mapped_column(Integer,default=0)
    last_error_code:Mapped[str|None]=mapped_column(String(45),nullable=True)
    sent_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint('tenant_id','idempotency_key'),)


class PatientConsentChallenge(TenantEntity,Base):
    __tablename__='patient_consent_challenges'
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),index=True)
    token_hash:Mapped[str]=mapped_column(String(64),unique=True,index=True)
    purpose:Mapped[str]=mapped_column(String(40))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    used_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    issued_by:Mapped[str]=mapped_column(ForeignKey('users.id'))

# Section 07 records hold only metadata and non-PHI references. A credential
# attested by a local administrator is NOT independent medical accreditation.
class ReviewerCredential(TenantEntity,Base):
    __tablename__='reviewer_credentials'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False,index=True)
    issuing_country:Mapped[str]=mapped_column(String(2),nullable=False)
    issuing_authority:Mapped[str]=mapped_column(String(120),nullable=False)
    verification_reference:Mapped[str]=mapped_column(String(100),nullable=False)
    checked_by:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    checked_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    status:Mapped[str]=mapped_column(String(32),default='locally_attested',nullable=False)
    __table_args__=(UniqueConstraint('tenant_id','user_id'),)

class IntakeReviewRecord(TenantEntity,Base):
    __tablename__='intake_review_records'
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'),index=True,nullable=False)
    intake_id:Mapped[str]=mapped_column(ForeignKey('patient_intakes.id'),index=True,nullable=False)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    action:Mapped[str]=mapped_column(String(55),nullable=False)
    reference:Mapped[str]=mapped_column(String(100),nullable=False)
    # Never infer provider or emergency-service contact success from this row.
    external_confirmation:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    __table_args__=(UniqueConstraint('tenant_id','intake_id','action','reference'),)

class IntakeReviewerAssignment(TenantEntity,Base):
    __tablename__='intake_reviewer_assignments'
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'),index=True,nullable=False)
    intake_id:Mapped[str]=mapped_column(ForeignKey('patient_intakes.id'),index=True,nullable=False)
    reviewer_user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False,index=True)
    assigned_by:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    active:Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    __table_args__=(UniqueConstraint('tenant_id','intake_id','reviewer_user_id'),)


class MedicalDocumentEvent(TenantEntity,Base):
    """PHI-free access trail; patient portal access is not impersonated as a staff user."""
    __tablename__ = 'medical_document_events'
    document_id:Mapped[str]=mapped_column(ForeignKey('documents.id'),nullable=False,index=True)
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'),nullable=False,index=True)
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),nullable=False)
    actor_type:Mapped[str]=mapped_column(String(20),nullable=False)
    staff_user_id:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    portal_access_id:Mapped[str|None]=mapped_column(ForeignKey('portal_access.id'),nullable=True)
    action:Mapped[str]=mapped_column(String(40),nullable=False)
    __table_args__=(Index('idx_medical_document_events_tenant_case','tenant_id','case_id'),)


# Section 09: tenant-scoped, metadata-only patient CRM coordination.
# These entities never approve clinical treatment or transmit messages.
class CRMFollowUp(TenantEntity, Base):
    __tablename__ = 'crm_followups'
    case_id:Mapped[str]=mapped_column(ForeignKey('cases.id'),nullable=False,index=True)
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),nullable=False,index=True)
    assigned_user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    idempotency_key:Mapped[str]=mapped_column(String(100),nullable=False)
    due_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    reason_code:Mapped[str]=mapped_column(String(40),nullable=False)
    status:Mapped[str]=mapped_column(String(35),default='open',nullable=False)
    outcome_code:Mapped[str|None]=mapped_column(String(40),nullable=True)
    completion_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    resolved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(
        UniqueConstraint('tenant_id','case_id','idempotency_key'),
        Index('idx_crm_followups_queue','tenant_id','status','due_at'),
    )

class CRMDuplicateReview(TenantEntity, Base):
    __tablename__ = 'crm_duplicate_reviews'
    left_patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),nullable=False)
    right_patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'),nullable=False)
    decision:Mapped[str]=mapped_column(String(32),nullable=False)
    reviewer_user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    evidence_reference:Mapped[str]=mapped_column(String(100),nullable=False)
    # Relationship is a non-destructive review record, NEVER a data/consent merge.
    __table_args__=(UniqueConstraint('tenant_id','left_patient_id','right_patient_id'),)

# Section 11: administrative inbox state and PHI-free action history.
class InboxThread(TenantEntity, Base):
    __tablename__ = 'inbox_threads'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default='open', nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default='normal', nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__=(UniqueConstraint('tenant_id','conversation_id'),Index('idx_inbox_queue','tenant_id','status','priority'),)

class InboxAction(TenantEntity, Base):
    __tablename__ = 'inbox_actions'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), nullable=False, index=True)
    actor_user_id: Mapped[str|None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reference: Mapped[str|None] = mapped_column(String(100), nullable=True)
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    target_user_id: Mapped[str|None] = mapped_column(ForeignKey('users.id'),nullable=True)


# Section 12 — directory management and access to a physician-specific portal.
# "locally_attested" is administrative evidence, NOT external licensure validation.
class PhysicianAccount(TenantEntity, Base):
    __tablename__ = "physician_accounts"
    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    linked_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "physician_id"), UniqueConstraint("tenant_id", "user_id"))

class PhysicianCredential(TenantEntity, Base):
    __tablename__ = "physician_credentials"
    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), nullable=False, index=True)
    issuing_country: Mapped[str] = mapped_column(String(2), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(120), nullable=False)
    license_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="locally_attested", nullable=False)
    reviewed_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "physician_id"),)

class PhysicianAffiliation(TenantEntity, Base):
    __tablename__ = "physician_affiliations"
    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), nullable=False, index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="locally_recorded", nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "physician_id", "hospital_id"),)

class PhysicianAvailability(TenantEntity, Base):
    __tablename__ = "physician_availability"
    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    __table_args__ = (Index("idx_physician_availability_tenant_window", "tenant_id", "physician_id", "starts_at"),)

# Section 13: hospital coordination metadata; local attestations are NOT
# independent hospital licensing or official provider confirmations.
class HospitalAccount(TenantEntity, Base):
    __tablename__ = "hospital_accounts"
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    linked_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "hospital_id", "user_id"), UniqueConstraint("tenant_id", "user_id"))

class HospitalCredential(TenantEntity, Base):
    __tablename__ = "hospital_credentials"
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False, index=True)
    issuing_country: Mapped[str] = mapped_column(String(2), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(120), nullable=False)
    registration_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="locally_attested")
    checked_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "hospital_id"),)

class HospitalService(TenantEntity, Base):
    __tablename__ = "hospital_services"
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="locally_recorded")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "hospital_id", "service_code"),)

class HospitalCapacity(TenantEntity, Base):
    __tablename__ = "hospital_capacity"
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(48), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    proposed_units: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    __table_args__ = (Index("idx_hospital_capacity_window", "tenant_id", "hospital_id", "starts_at"),)

class HospitalCoordination(TenantEntity, Base):
    __tablename__ = "hospital_coordinations"
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(48), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    last_actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "hospital_id", "case_id", "reference"),)

# Section 14 - nonclinical provider options are proposals requiring human review.
class ProviderMatch(TenantEntity, Base):
    __tablename__="provider_matches"
    case_id:Mapped[str]=mapped_column(ForeignKey("cases.id"),nullable=False,index=True)
    patient_id:Mapped[str]=mapped_column(ForeignKey("patients.id"),nullable=False)
    physician_id:Mapped[str]=mapped_column(ForeignKey("physicians.id"),nullable=False)
    hospital_id:Mapped[str|None]=mapped_column(ForeignKey("hospitals.id"),nullable=True)
    status:Mapped[str]=mapped_column(String(30),nullable=False,default="pending_human_review")
    proposed_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    review_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","case_id","physician_id","hospital_id"),)

# Section 15: internally held calendar slots never certify external bookings.
class AppointmentSlot(TenantEntity,Base):
    __tablename__="appointment_slots"
    appointment_id:Mapped[str]=mapped_column(ForeignKey("appointments.id"),nullable=False,unique=True)
    case_id:Mapped[str]=mapped_column(ForeignKey("cases.id"),nullable=False)
    patient_id:Mapped[str]=mapped_column(ForeignKey("patients.id"),nullable=False)
    physician_id:Mapped[str]=mapped_column(ForeignKey("physicians.id"),nullable=False)
    availability_id:Mapped[str|None]=mapped_column(ForeignKey("physician_availability.id"),nullable=True)
    ends_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default="requested")
    request_key:Mapped[str]=mapped_column(String(100),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    review_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","case_id","request_key"),Index("idx_appointment_slots_resource","tenant_id","physician_id","status"),)

# Section 16: immutable financial quotation versions (administrative only).
class QuoteVersion(TenantEntity,Base):
    __tablename__="quote_versions"
    quote_id:Mapped[str]=mapped_column(ForeignKey("quotes.id"),nullable=False,index=True)
    case_id:Mapped[str]=mapped_column(ForeignKey("cases.id"),nullable=False)
    version:Mapped[int]=mapped_column(Integer,nullable=False)
    currency:Mapped[str]=mapped_column(String(3),nullable=False)
    lines_json:Mapped[str]=mapped_column(Text,nullable=False)
    total_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    status:Mapped[str]=mapped_column(String(32),nullable=False,default="draft")
    created_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    approval_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","quote_id","version"),)

# Section 16 financial hardening: manually sourced FX quoted as a rational
# minor-unit conversion. Never a live exchange rate, regulator-validated rate,
# or authorization to charge a patient.
class VerifiedFxRate(TenantEntity,Base):
    __tablename__="verified_fx_rates"
    source_currency:Mapped[str]=mapped_column(String(3),nullable=False)
    target_currency:Mapped[str]=mapped_column(String(3),nullable=False)
    numerator:Mapped[int]=mapped_column(BigInteger,nullable=False)
    denominator:Mapped[int]=mapped_column(BigInteger,nullable=False)
    source_reference:Mapped[str]=mapped_column(String(180),nullable=False)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    reviewed_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    __table_args__=(Index("idx_fx_rates_tenant_pair","tenant_id","source_currency","target_currency"),)


# Section 17 - administrative visa coordination with no passport/PHI fields.
# All references denote human-entered metadata; no government API is connected.
class MedicalVisa(TenantEntity, Base):
    __tablename__ = "medical_visas"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    origin_country: Mapped[str] = mapped_column(String(2), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(2), nullable=False)
    visa_type: Mapped[str] = mapped_column(String(24), nullable=False)
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    intended_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_action_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(36), nullable=False, default="requested")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    authority_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision_reported: Mapped[str | None] = mapped_column(String(40), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "request_key"),
        Index("idx_medical_visas_due", "tenant_id", "status", "next_action_due_at"),
    )

class MedicalVisaChecklist(TenantEntity, Base):
    __tablename__ = "medical_visa_checklist"
    application_id: Mapped[str] = mapped_column(ForeignKey("medical_visas.id"), nullable=False)
    item_key: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    review_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "application_id", "item_key"),)

class MedicalVisaEvent(TenantEntity, Base):
    __tablename__ = "medical_visa_events"
    application_id: Mapped[str] = mapped_column(ForeignKey("medical_visas.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    old_status: Mapped[str] = mapped_column(String(36), nullable=False)
    new_status: Mapped[str] = mapped_column(String(36), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "application_id", "step_key"),)


# Section 18: hotel records are manually supplied coordination metadata, NOT
# live hotel inventory, independent hotel partner validation or bookings.
class AccommodationProperty(TenantEntity, Base):
    __tablename__ = "accommodation_properties"
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="locally_recorded")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

class AccommodationInventory(TenantEntity, Base):
    __tablename__ = "accommodation_inventory"
    property_id: Mapped[str] = mapped_column(ForeignKey("accommodation_properties.id"), nullable=False)
    room_type: Mapped[str] = mapped_column(String(24), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    proposed_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    __table_args__ = (Index("idx_accommodation_inventory_windows",
        "tenant_id", "property_id", "room_type", "starts_on", "ends_on"),)

class AccommodationStay(TenantEntity, Base):
    __tablename__ = "accommodation_stays"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    property_id: Mapped[str] = mapped_column(ForeignKey("accommodation_properties.id"), nullable=False)
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    room_type: Mapped[str] = mapped_column(String(24), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    rooms_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory_id: Mapped[str | None] = mapped_column(ForeignKey("accommodation_inventory.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="requested")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    internal_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "request_key"),
        Index("idx_accommodation_stay_allocation",
              "tenant_id", "property_id", "inventory_id", "status", "starts_on", "ends_on"),
    )

class AccommodationEvent(TenantEntity, Base):
    __tablename__ = "accommodation_events"
    stay_id: Mapped[str] = mapped_column(ForeignKey("accommodation_stays.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    old_status: Mapped[str] = mapped_column(String(40), nullable=False)
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "stay_id", "step_key"),)


# Section 19: administrative resource availability; no real dispatch or clinical data.
class TravelResource(TenantEntity,Base):
    __tablename__="travel_resources"
    kind:Mapped[str]=mapped_column(String(24),nullable=False)
    label:Mapped[str]=mapped_column(String(120),nullable=False)
    city:Mapped[str]=mapped_column(String(80),nullable=False)
    seats:Mapped[int]=mapped_column(Integer,nullable=False)
    language:Mapped[str|None]=mapped_column(String(10),nullable=True)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default="locally_attested")
    recorded_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)

class TravelResourceWindow(TenantEntity,Base):
    __tablename__="travel_resource_windows"
    resource_id:Mapped[str]=mapped_column(ForeignKey("travel_resources.id"),nullable=False)
    starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    ends_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    reference:Mapped[str]=mapped_column(String(100),nullable=False)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default="proposed")
    recorded_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    __table_args__=(Index("idx_travel_windows_resource","tenant_id","resource_id","starts_at"),)

class TravelAssignment(TenantEntity,Base):
    __tablename__="travel_assignments"
    case_id:Mapped[str]=mapped_column(ForeignKey("cases.id"),nullable=False)
    patient_id:Mapped[str]=mapped_column(ForeignKey("patients.id"),nullable=False)
    resource_id:Mapped[str]=mapped_column(ForeignKey("travel_resources.id"),nullable=False)
    request_key:Mapped[str]=mapped_column(String(100),nullable=False)
    kind:Mapped[str]=mapped_column(String(40),nullable=False)
    starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    ends_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    passengers:Mapped[int]=mapped_column(Integer,nullable=False)
    language:Mapped[str|None]=mapped_column(String(10),nullable=True)
    origin_zone:Mapped[str]=mapped_column(String(30),nullable=False)
    destination_zone:Mapped[str]=mapped_column(String(30),nullable=False)
    window_id:Mapped[str|None]=mapped_column(ForeignKey("travel_resource_windows.id"),nullable=True)
    status:Mapped[str]=mapped_column(String(40),nullable=False,default="requested")
    reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    supplier_name:Mapped[str|None]=mapped_column(String(100),nullable=True)
    supplier_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    created_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    __table_args__=(UniqueConstraint("tenant_id","case_id","request_key"),
        Index("idx_travel_assignment_resource","tenant_id","resource_id","status","starts_at","ends_at"),)

class TravelAssignmentEvent(TenantEntity,Base):
    __tablename__="travel_assignment_events"
    request_id:Mapped[str]=mapped_column(ForeignKey("travel_assignments.id"),nullable=False)
    actor_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    step_key:Mapped[str]=mapped_column(String(100),nullable=False)
    fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    action:Mapped[str]=mapped_column(String(40),nullable=False)
    old_status:Mapped[str]=mapped_column(String(40),nullable=False)
    new_status:Mapped[str]=mapped_column(String(40),nullable=False)
    reference:Mapped[str]=mapped_column(String(100),nullable=False)
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(UniqueConstraint("tenant_id","request_id","step_key"),)


# Section 20: agent access, agreements and opaque referrals. Alpha: no compensation payout.
class AgentAgreement(TenantEntity,Base):
    __tablename__="agent_agreements"
    agent_id:Mapped[str]=mapped_column(ForeignKey("agents.id"),nullable=False)
    contract_key:Mapped[str]=mapped_column(String(100),nullable=False)
    jurisdiction:Mapped[str]=mapped_column(String(2),nullable=False)
    currency:Mapped[str]=mapped_column(String(3),nullable=False)
    max_budget_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    scope:Mapped[str]=mapped_column(String(80),nullable=False)
    status:Mapped[str]=mapped_column(String(30),nullable=False,default="draft")
    document_reference:Mapped[str|None]=mapped_column(String(100),nullable=True)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","agent_id","contract_key"),)

class AgentIdentity(TenantEntity,Base):
    __tablename__="agent_identities"
    agent_id:Mapped[str]=mapped_column(ForeignKey("agents.id"),nullable=False)
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    provisioned_by:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    __table_args__=(UniqueConstraint("tenant_id","user_id"),UniqueConstraint("tenant_id","agent_id"),)

class AgentReferralIntent(TenantEntity,Base):
    __tablename__="agent_referral_intents"
    agent_id:Mapped[str]=mapped_column(ForeignKey("agents.id"),nullable=False)
    agreement_id:Mapped[str]=mapped_column(ForeignKey("agent_agreements.id"),nullable=False)
    request_key:Mapped[str]=mapped_column(String(100),nullable=False)
    channel:Mapped[str]=mapped_column(String(30),nullable=False)
    campaign_code:Mapped[str]=mapped_column(String(60),nullable=False)
    status:Mapped[str]=mapped_column(String(30),nullable=False,default="submitted")
    patient_id:Mapped[str|None]=mapped_column(ForeignKey("patients.id"),nullable=True)
    matched_by:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","agent_id","request_key"),
        UniqueConstraint("tenant_id","patient_id"),Index("idx_agent_intents_by_agent","tenant_id","agent_id","status"),)

class AgentCommercialDraft(TenantEntity,Base):
    __tablename__="agent_commercial_drafts"
    agent_id:Mapped[str]=mapped_column(ForeignKey("agents.id"),nullable=False)
    agreement_id:Mapped[str]=mapped_column(ForeignKey("agent_agreements.id"),nullable=False)
    draft_key:Mapped[str]=mapped_column(String(100),nullable=False)
    activity_reference:Mapped[str]=mapped_column(String(100),nullable=False)
    amount_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    status:Mapped[str]=mapped_column(String(48),nullable=False,default="blocked_legal_review")
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    __table_args__=(UniqueConstraint("tenant_id","agent_id","draft_key"),)

class AgentGovernanceEvent(TenantEntity,Base):
    __tablename__="agent_governance_events"
    agent_id:Mapped[str]=mapped_column(ForeignKey("agents.id"),nullable=False)
    actor_id:Mapped[str]=mapped_column(ForeignKey("users.id"),nullable=False)
    entity_kind:Mapped[str]=mapped_column(String(40),nullable=False)
    entity_id:Mapped[str]=mapped_column(String(36),nullable=False)
    action:Mapped[str]=mapped_column(String(48),nullable=False)
    reference:Mapped[str]=mapped_column(String(100),nullable=False,default="")
