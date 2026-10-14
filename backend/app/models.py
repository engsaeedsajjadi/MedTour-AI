from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def uid(): return str(uuid4())
def utcnow(): return datetime.now(timezone.utc)

class Tenant(Base):
    __tablename__ = 'tenants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class TenantEntity:
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True, nullable=False)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class User(TenantEntity, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(250), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('tenant_id', 'email'),)

class Patient(TenantEntity, Base):
    __tablename__ = 'patients'
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(100), default='')
    language: Mapped[str] = mapped_column(String(10), default='en')
    contact: Mapped[str] = mapped_column(String(200), default='')
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)

class Case(TenantEntity, Base):
    __tablename__ = 'cases'
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), nullable=False)
    complaint: Mapped[str] = mapped_column(Text, default='')
    specialty: Mapped[str] = mapped_column(String(100), default='')
    status: Mapped[str] = mapped_column(String(50), default='new')
    assigned_operator_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)

class Consent(TenantEntity, Base):
    __tablename__ = 'consents'
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    purpose: Mapped[str] = mapped_column(String(80))
    accepted: Mapped[bool] = mapped_column(Boolean)
    notice_version: Mapped[str] = mapped_column(String(40))

class Document(TenantEntity, Base):
    __tablename__ = 'documents'
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'))
    filename: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(70), default='report')
    status: Mapped[str] = mapped_column(String(40), default='storage_not_configured')
    storage_key: Mapped[str | None] = mapped_column(String(350), nullable=True)

class Physician(TenantEntity, Base):
    __tablename__ = 'physicians'
    full_name: Mapped[str] = mapped_column(String(200))
    specialty: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(100), default='')
    credential_status: Mapped[str] = mapped_column(String(40), default='unverified')

class Hospital(TenantEntity, Base):
    __tablename__ = 'hospitals'
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), default='')
    license_status: Mapped[str] = mapped_column(String(40), default='unverified')

class Referral(TenantEntity, Base):
    __tablename__ = 'referrals'
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'))
    physician_id: Mapped[str] = mapped_column(ForeignKey('physicians.id'))
    status: Mapped[str] = mapped_column(String(40), default='requested')
    reviewer_note: Mapped[str] = mapped_column(Text, default='')

class Appointment(TenantEntity, Base):
    __tablename__ = 'appointments'
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'))
    physician_id: Mapped[str] = mapped_column(ForeignKey('physicians.id'))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default='requested')
    confirmation_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

class Quote(TenantEntity, Base):
    __tablename__ = 'quotes'
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'))
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(Integer)
    details: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(40), default='draft')
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)

class TravelRequest(TenantEntity, Base):
    __tablename__ = 'travel_requests'
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'))
    service_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default='requested')
    notes: Mapped[str] = mapped_column(Text, default='')
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

class Conversation(TenantEntity, Base):
    __tablename__ = 'conversations'
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    channel: Mapped[str] = mapped_column(String(30), default='webchat')
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    human_handoff: Mapped[bool] = mapped_column(Boolean, default=False)

class Message(TenantEntity, Base):
    __tablename__ = 'messages'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'))
    sender: Mapped[str] = mapped_column(String(30))
    language: Mapped[str] = mapped_column(String(10), default='en')
    body: Mapped[str] = mapped_column(Text)

class Task(TenantEntity, Base):
    __tablename__ = 'tasks'
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default='open')

class Audit(TenantEntity, Base):
    __tablename__ = 'audit_events'
    user_id: Mapped[str] = mapped_column(String(36))
    event: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(36))
