"""Additional operational entities. These are coordination records, NOT clinical orders."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, BigInteger, String, Text, UniqueConstraint, Index
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

class ContentPage(TenantEntity,Base):
    __tablename__='content_pages'
    slug:Mapped[str]=mapped_column(String(150))
    locale:Mapped[str]=mapped_column(String(10))
    title:Mapped[str]=mapped_column(String(250))
    body:Mapped[str]=mapped_column(Text,default='')
    status:Mapped[str]=mapped_column(String(24),default='draft')
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    __table_args__=(UniqueConstraint('tenant_id','slug','locale'),)

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
