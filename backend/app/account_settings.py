"""Self-service settings: each staff member's own profile and sessions, and the organization
profile that administrators maintain from the panel.

Secrets (SMTP password, bot token, encryption keys) are deliberately NOT editable here; they
stay in the server environment. Integration status is shown read-only so administrators can
see what still needs configuring.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .enterprise_models import RefreshSession, StaffTotp, TenantSetting
from .models import Audit, Tenant, User
from .security import current_user, roles, secret, staff_mfa_required

router = APIRouter(prefix="/api/v1", tags=["self-service settings"])
LANGS = ("fa", "ar", "en", "ps", "prs")
CURRENCIES = ("USD", "EUR", "IRR", "AED", "TRY", "IQD", "AFN", "GBP")
ORG_KEY = "organization_profile"
TEXT = r"^[^\x00-\x1F\x7F<>]+$"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_key(user: User) -> str:
    return "user_prefs:" + user.id


def _read(db: Session, tenant_id: str, key: str) -> dict:
    row = db.scalar(select(TenantSetting).where(TenantSetting.tenant_id == tenant_id, TenantSetting.key == key))
    try:
        value = json.loads(row.value_json) if row else {}
    except ValueError:
        value = {}
    return value if isinstance(value, dict) else {}


def _write(db: Session, user: User, key: str, value: dict, event: str) -> None:
    serial = json.dumps(value, ensure_ascii=False)
    row = db.scalar(select(TenantSetting).where(TenantSetting.tenant_id == user.tenant_id,
                                                TenantSetting.key == key).with_for_update())
    if row is None:
        db.add(TenantSetting(tenant_id=user.tenant_id, key=key, value_json=serial))
    else:
        row.value_json = serial
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id, event=event,
                 entity_type="TenantSetting", entity_id=user.id))
    db.commit()


def _public_https(value: str) -> bool:
    from .telegram import _public_https_url
    return _public_https_url(value)


# ---------------------------------------------------------------- personal settings

class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(default="", max_length=80)
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    calendar: Literal["jalali", "gregorian"] = "jalali"
    digits: Literal["persian", "latin"] = "persian"
    # Page opened after sign-in; empty means the default page of the user's role.
    start_page: str = Field(default="", max_length=40, pattern=r"^([a-z][a-z-]{1,39})?$")

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if value and (len(value) < 2 or not re.fullmatch(TEXT, value)):
            raise ValueError("Display name must be 2-80 plain characters")
        return value

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("Unknown time zone")
        return value


def _sessions(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(RefreshSession).where(
        RefreshSession.tenant_id == user.tenant_id, RefreshSession.user_id == user.id,
        RefreshSession.revoked_at.is_(None), RefreshSession.expires_at > _now(),
    ).order_by(RefreshSession.created_at.desc()).limit(20)).all()
    return [{"started_at": r.created_at, "last_used_at": r.last_rotated_at or r.created_at,
             "expires_at": r.expires_at, "two_factor": bool(r.mfa_verified)} for r in rows]


@router.get("/account/profile")
def my_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    prefs = _read(db, user.tenant_id, _user_key(user))
    totp = db.scalar(select(StaffTotp).where(StaffTotp.tenant_id == user.tenant_id, StaffTotp.user_id == user.id))
    tenant = db.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
    return {"email": user.email, "role": user.role, "organization_slug": tenant.slug if tenant else "",
            "display_name": prefs.get("display_name", ""), "timezone": prefs.get("timezone", "Asia/Tehran"),
            "calendar": prefs.get("calendar", "jalali"), "digits": prefs.get("digits", "persian"),
            "start_page": prefs.get("start_page", ""),
            "two_factor_enabled": bool(totp and totp.enabled),
            "two_factor_required": staff_mfa_required(user.role) or organization_requires_mfa(db, user),
            "sessions": _sessions(db, user)}


@router.put("/account/profile")
def update_my_profile(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _write(db, user, _user_key(user), body.model_dump(), "staff_profile_updated")
    return my_profile(db, user)


@router.post("/account/sessions/sign-out-others")
def sign_out_other_sessions(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """End every other signed-in device; this browser receives fresh tokens with the same assurance."""
    from .identity_access import invalidate_sessions
    from .security import token_for
    from .session_api import issue_refresh
    raw = request.headers.get("authorization", "").split(" ", 1)[-1]
    try:
        claims = jwt.decode(raw, secret(), algorithms=["HS256"], options={"verify_exp": False})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token") from None
    mfa = claims.get("mfa") is True
    db.scalar(select(User.id).where(User.tenant_id == user.tenant_id, User.id == user.id).with_for_update())
    invalidate_sessions(db, user)
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id, event="staff_other_sessions_revoked",
                 entity_type="User", entity_id=user.id))
    db.commit()
    db.refresh(user)
    return {"access_token": token_for(user, mfa_verified=mfa),
            "refresh_token": issue_refresh(db, user, mfa_verified=mfa), "token_type": "bearer"}


# ---------------------------------------------------------------- organization settings

class OrganizationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=2, max_length=120, pattern=TEXT)
    contact_email: str = Field(default="", max_length=190)
    contact_phone: str = Field(default="", max_length=30)
    website: str = Field(default="", max_length=300)
    privacy_notice_url: str = Field(default="", max_length=300)
    patient_support_hours: str = Field(default="", max_length=120)
    default_language: Literal["fa", "ar", "en", "ps", "prs"] = "fa"
    enabled_languages: list[Literal["fa", "ar", "en", "ps", "prs"]] = Field(default_factory=lambda: list(LANGS))
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    default_currency: Literal["USD", "EUR", "IRR", "AED", "TRY", "IQD", "AFN", "GBP"] = "USD"
    # Version label of the published privacy notice; recorded with every consent the patient gives.
    privacy_notice_version: str = Field(default="v1", min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
    # Public link the Telegram bot's "contact operator" button opens (e.g. https://t.me/<operator>).
    telegram_operator_url: str = Field(default="", max_length=300)
    # Name in Latin letters for PDF documents (PDFs use a Latin font).
    latin_name: str = Field(default="", max_length=100, pattern=r"^([A-Za-z0-9][A-Za-z0-9 .,&'()/-]{1,99})?$")
    quote_validity_days: int = Field(default=30, ge=1, le=180)
    quote_footer_note: str = Field(default="", max_length=200, pattern=r"^[\x20-\x7E]*$")
    # Names picked from lists instead of retyped for every case (Latin, as the records require).
    visa_authorities: list[str] = Field(default_factory=list, max_length=30)
    supplier_desks: list[str] = Field(default_factory=list, max_length=50)
    # Extra staff roles that must use two-step sign-in (admin/operator may already be required by the server).
    two_factor_roles: list[Literal["admin", "operator", "hospital", "physician", "doctor", "agent", "cms_editor"]] = Field(default_factory=list)

    @field_validator("contact_email")
    @classmethod
    def email(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,}", value):
            raise ValueError("Invalid email")
        return value

    @field_validator("contact_phone")
    @classmethod
    def phone(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"\+?[0-9 ()-]{6,30}", value):
            raise ValueError("Invalid phone number")
        return value

    @field_validator("website", "privacy_notice_url", "telegram_operator_url")
    @classmethod
    def https(cls, value: str) -> str:
        value = value.strip()
        if value and not _public_https(value):
            raise ValueError("Use a public https:// address without query or fragment")
        return value

    @field_validator("patient_support_hours")
    @classmethod
    def hours(cls, value: str) -> str:
        value = " ".join(value.split())
        if value and not re.fullmatch(TEXT, value):
            raise ValueError("Plain text only")
        return value

    @field_validator("timezone")
    @classmethod
    def zone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("Unknown time zone")
        return value

    @field_validator("visa_authorities", "supplier_desks")
    @classmethod
    def names(cls, value: list[str]) -> list[str]:
        clean = []
        for item in value:
            item = " ".join(str(item).split())
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._/-]{5,99}", item):
                raise ValueError("Each name: 6-100 Latin letters, digits, space . _ / -")
            if item not in clean:
                clean.append(item)
        return clean

    @field_validator("two_factor_roles")
    @classmethod
    def unique_roles(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @field_validator("enabled_languages")
    @classmethod
    def langs(cls, value: list[str]) -> list[str]:
        if not value or len(set(value)) != len(value):
            raise ValueError("Choose at least one language, without duplicates")
        return value


def organization_profile(db: Session, tenant_id: str) -> dict:
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    defaults = OrganizationIn(display_name=(tenant.name if tenant and len(tenant.name) >= 2 else "MedTour AI")).model_dump()
    stored = _read(db, tenant_id, ORG_KEY)
    return {**defaults, **{k: v for k, v in stored.items() if k in defaults}}


OPERATOR_URL_KEY = "medtour:telegram:operator_url"


def bot_owner(db: Session, tenant_id: str) -> bool:
    """One Telegram bot per deployment: it belongs to TELEGRAM_OWNER_TENANT_SLUG, or to the first
    organization created when that is not set (a single-organization installation)."""
    slug = os.getenv("TELEGRAM_OWNER_TENANT_SLUG", "").strip().lower()
    from .tenant_context import system_scope
    with system_scope(db):
        if slug:
            owner = db.scalar(select(Tenant.id).where(Tenant.slug == slug))
        else:
            owner = db.scalar(select(Tenant.id).order_by(Tenant.created_at, Tenant.id).limit(1))
    return owner == tenant_id


def publish_operator_url(url: str) -> bool:
    """Hand the link to the Telegram services through Redis (they have no database access)."""
    uri = os.getenv("REDIS_URL", "")
    if not uri:
        return False
    try:
        import redis
        client = redis.Redis.from_url(uri, socket_connect_timeout=1, socket_timeout=2)
        if url:
            client.set(OPERATOR_URL_KEY, url)
        else:
            client.delete(OPERATOR_URL_KEY)
        return True
    except Exception:
        return False


def _ai_status() -> dict:
    """Non-secret view of the AI provider configuration; the key itself is never returned."""
    from .ai import approved_provider_base_url, provider_available
    from urllib.parse import urlsplit
    base = approved_provider_base_url()
    return {"provider_ready": provider_available(),
            "provider_approved": os.getenv("AI_PROVIDER_APPROVED", "").lower() == "true",
            "model": os.getenv("AI_MODEL", ""), "host": urlsplit(base).hostname if base else "",
            "key_configured": bool(os.getenv("AI_API_KEY")),
            "assistants_allowed_in_this_environment": os.getenv("APP_ENV", "development").lower() in ("development", "test")}


def organization_requires_mfa(db: Session, user: User) -> bool:
    """The organization may require two-step sign-in for more roles than the server does."""
    return user.role in organization_profile(db, user.tenant_id).get("two_factor_roles", [])


def _integrations(user: User, operator_url: str = "") -> dict:
    from . import otp_delivery
    from .secure_media import s3_ready
    polling = os.getenv("TELEGRAM_POLLING_ENABLED", "").lower() == "true"
    webhook = os.getenv("TELEGRAM_BOT_ENABLED", "").lower() == "true"
    return {
        "telegram": {"mode": "webhook" if webhook else "polling_test" if polling else "off",
                     "operator_link_configured": bool(operator_url or os.getenv("PUBLIC_OPERATOR_CONTACT_URL"))},
        "patient_code_delivery": otp_delivery.provider() if otp_delivery.configured() else "not_configured",
        "secure_document_storage": "object_storage_scanned" if s3_ready() else "not_configured",
        "staff_two_factor_required": staff_mfa_required(user.role) or staff_mfa_required("admin"),
        "ai": _ai_status(),
        "whatsapp_outbound_approved": os.getenv("WHATSAPP_OUTBOUND_APPROVED", "").lower() == "true",
        "voice_processing_approved": os.getenv("VOICE_PROCESSOR_APPROVED", "").lower() == "true",
        "environment": os.getenv("APP_ENV", "development"),
        "managed_on_server": ["SMTP_PASSWORD", "TELEGRAM_BOT_TOKEN", "AI_API_KEY", "MEDICAL_MASTER_KEY", "MFA_ENCRYPTION_KEY"],
    }


@router.get("/organization/profile")
def read_organization(db: Session = Depends(get_db), user: User = Depends(current_user)):
    profile = organization_profile(db, user.tenant_id)
    owner = bot_owner(db, user.tenant_id)
    data = {"profile": profile, "editable": user.role == "admin", "telegram_bot_owner": owner}
    if user.role == "admin":
        data["integrations"] = _integrations(user, profile["telegram_operator_url"] if owner else "")
    return data


@router.put("/organization/profile")
def update_organization(body: OrganizationIn, db: Session = Depends(get_db), user: User = Depends(roles("admin"))):
    value = body.model_dump()
    if value["default_language"] not in value["enabled_languages"]:
        raise HTTPException(422, "Default language must be one of the enabled languages")
    if value["two_factor_roles"]:
        from .identity_access import encryption_key
        try:
            encryption_key()
        except HTTPException:
            raise HTTPException(422, "Two-step sign-in cannot be required: the server's MFA_ENCRYPTION_KEY is not set") from None
    owner = bot_owner(db, user.tenant_id)
    if not owner:
        # Only the organization that owns this deployment's bot may point its button somewhere.
        value["telegram_operator_url"] = organization_profile(db, user.tenant_id)["telegram_operator_url"]
    _write(db, user, ORG_KEY, value, "organization_profile_updated")
    if owner:
        publish_operator_url(value["telegram_operator_url"])
    return read_organization(db, user)


def enabled_languages(db: Session, tenant_id: str) -> list[str]:
    return list(organization_profile(db, tenant_id)["enabled_languages"])


@router.get("/portal/organization")
def portal_organization(x_patient_access: str | None = Header(None, alias="X-Patient-Access"),
                        db: Session = Depends(get_db)):
    """What the patient needs to reach the organization; nothing internal."""
    from .patient_portal import portal_session
    grant = portal_session(x_patient_access, db)
    p = organization_profile(db, grant.tenant_id)
    return {k: p[k] for k in ("display_name", "contact_email", "contact_phone", "website",
                              "privacy_notice_url", "privacy_notice_version", "patient_support_hours", "timezone")}
