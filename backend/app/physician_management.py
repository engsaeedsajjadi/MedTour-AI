"""Section 12 administrative physician management (synthetic Alpha).

A staff assertion or license reference is NOT independent regulator verification.
The physician portal is restricted to an explicitly linked active user and
current locally attested credential metadata; no raw patient data is exposed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Physician, Hospital, User, Audit, Referral, Appointment, Case
from .enterprise_models import (
    PhysicianAccount, PhysicianCredential, PhysicianAffiliation,
    PhysicianAvailability,
)
from .security import roles

router = APIRouter(prefix="/api/v1/physician-management", tags=["physician management"])
staff = roles("admin", "operator")
admin = roles("admin")
physician = roles("physician")
REF = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"


def now():
    return datetime.now(timezone.utc)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def directory_doctor(db: Session, user: User, pid: str) -> Physician:
    result = db.scalar(select(Physician).where(
        Physician.tenant_id == user.tenant_id, Physician.id == pid,
    ))
    if result is None:
        raise HTTPException(404, "Physician not found in tenant")
    return result


def event(db: Session, actor: User, action: str, kind: str, entity_id: str):
    db.add(Audit(
        tenant_id=actor.tenant_id, user_id=actor.id,
        event="physician_" + action, entity_type=kind, entity_id=entity_id,
    ))


def credential_row(db: Session, tenant_id: str, pid: str):
    return db.scalar(select(PhysicianCredential).where(
        PhysicianCredential.tenant_id == tenant_id,
        PhysicianCredential.physician_id == pid,
    ))


def evidence_state(row) -> str:
    if row is None:
        return "missing"
    if row.status != "locally_attested":
        return "revoked"
    return "locally_attested" if utc(row.expires_at) > now() else "expired"


def doctor_summary(db: Session, doctor: Physician) -> dict:
    evidence = credential_row(db, doctor.tenant_id, doctor.id)
    account = db.scalar(select(PhysicianAccount).where(
        PhysicianAccount.tenant_id == doctor.tenant_id,
        PhysicianAccount.physician_id == doctor.id,
    ))
    affiliated = db.scalars(select(PhysicianAffiliation).where(
        PhysicianAffiliation.tenant_id == doctor.tenant_id,
        PhysicianAffiliation.physician_id == doctor.id,
        PhysicianAffiliation.status == "locally_recorded",
    ).limit(50)).all()
    return {
        "physician_id": doctor.id, "name": doctor.full_name,
        "specialty": doctor.specialty, "city": doctor.city,
        "directory_status": doctor.credential_status,
        "evidence_status": evidence_state(evidence),
        "evidence_expiry": evidence.expires_at if evidence else None,
        "linked_user_id": account.user_id if account and account.active else None,
        "hospital_ids": [row.hospital_id for row in affiliated],
        "regulator_licensure_verified": False,
        "clinical_authorization": False,
        "hospital_affiliations_externally_verified": False,
    }


@router.get("/directory")
def directory(
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(staff),
):
    rows = db.scalars(select(Physician).where(
        Physician.tenant_id == user.tenant_id,
    ).order_by(Physician.created_at.desc(), Physician.id).limit(limit)).all()
    return {"items": [doctor_summary(db, p) for p in rows],
            "limited": True, "externally_verified": False}


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str


@router.put("/physicians/{physician_id}/account")
def link_account(
    physician_id: str, body: LinkIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    doctor = directory_doctor(db, user, physician_id)
    account_user = db.scalar(select(User).where(
        User.id == body.user_id, User.tenant_id == user.tenant_id,
        User.role == "physician", User.active.is_(True),
    ))
    if account_user is None:
        raise HTTPException(404, "Active physician login not found")
    # Serializing the user row prevents concurrent admin requests for the
    # same user from binding to different directory entries.
    db.scalar(select(User.id).where(User.id == account_user.id,
             User.tenant_id == user.tenant_id).with_for_update())
    existing_user = db.scalar(select(PhysicianAccount).where(
        PhysicianAccount.tenant_id == user.tenant_id,
        PhysicianAccount.user_id == account_user.id,
    ))
    if existing_user and existing_user.physician_id != doctor.id:
        raise HTTPException(409, "This login belongs to another physician")
    existing = db.scalar(select(PhysicianAccount).where(
        PhysicianAccount.tenant_id == user.tenant_id,
        PhysicianAccount.physician_id == doctor.id,
    ).with_for_update())
    if existing and existing.user_id != account_user.id:
        raise HTTPException(409, "This physician already has a different login")
    if existing and existing.active:
        return {"physician_id": doctor.id, "user_id": account_user.id,
                "reused": True, "clinical_privileges": False}
    if existing:
        existing.active = True
        existing.linked_by = user.id
    else:
        db.add(PhysicianAccount(
            tenant_id=user.tenant_id, physician_id=doctor.id,
            user_id=account_user.id, linked_by=user.id, active=True,
        ))
    event(db, user, "account_linked", "Physician", doctor.id)
    db.commit()
    return {"physician_id": doctor.id, "user_id": account_user.id,
            "reused": False, "clinical_privileges": False}


@router.post("/physicians/{physician_id}/account/revoke")
def unlink_account(
    physician_id: str, db: Session = Depends(get_db),
    user: User = Depends(admin),
):
    directory_doctor(db, user, physician_id)
    row = db.scalar(select(PhysicianAccount).where(
        PhysicianAccount.tenant_id == user.tenant_id,
        PhysicianAccount.physician_id == physician_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "No linked account")
    if row.active:
        row.active = False
        event(db, user, "account_unlinked", "Physician", physician_id)
        db.commit()
    return {"physician_id": physician_id, "portal_access": False}


class CredentialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuing_country: str = Field(pattern=r"^[A-Z]{2}$")
    issuing_authority: str = Field(min_length=3, max_length=120)
    license_reference: str = Field(min_length=6, max_length=100, pattern=REF)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value):
        if value.tzinfo is None:
            raise ValueError("UTC offset required")
        if not now() + timedelta(days=1) <= value.astimezone(timezone.utc) <= now() + timedelta(days=1095):
            raise ValueError("Expiry must be between 1 and 1095 days from now")
        return value


@router.put("/physicians/{physician_id}/credential")
def attest_credential(
    physician_id: str, body: CredentialIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    directory_doctor(db, user, physician_id)
    row = db.scalar(select(PhysicianCredential).where(
        PhysicianCredential.tenant_id == user.tenant_id,
        PhysicianCredential.physician_id == physician_id,
    ).with_for_update())
    if row is None:
        row = PhysicianCredential(
            tenant_id=user.tenant_id, physician_id=physician_id,
            reviewed_by=user.id,
        )
        db.add(row)
    row.issuing_country = body.issuing_country
    row.issuing_authority = body.issuing_authority
    row.license_reference = body.license_reference
    row.reviewed_by = user.id
    row.reviewed_at = now()
    row.expires_at = utc(body.expires_at)
    row.status = "locally_attested"
    event(db, user, "evidence_locally_attested", "Physician", physician_id)
    db.commit()
    return {"physician_id": physician_id, "status": "locally_attested",
            "externally_verified": False,
            "clinical_decision_authorized": False}


@router.post("/physicians/{physician_id}/credential/revoke")
def revoke_credential(
    physician_id: str, db: Session = Depends(get_db),
    user: User = Depends(admin),
):
    directory_doctor(db, user, physician_id)
    row = db.scalar(select(PhysicianCredential).where(
        PhysicianCredential.tenant_id == user.tenant_id,
        PhysicianCredential.physician_id == physician_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "No credential evidence")
    if row.status != "revoked":
        row.status = "revoked"
        event(db, user, "evidence_revoked", "Physician", physician_id)
        db.commit()
    return {"physician_id": physician_id,
            "portal_authorized": False, "externally_verified": False}


class AffiliationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hospital_id: str


@router.post("/physicians/{physician_id}/affiliations")
def record_affiliation(
    physician_id: str, body: AffiliationIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    doctor = directory_doctor(db, user, physician_id)
    hospital = db.scalar(select(Hospital).where(
        Hospital.id == body.hospital_id, Hospital.tenant_id == user.tenant_id,
    ))
    if hospital is None:
        raise HTTPException(404, "Hospital not found")
    row = db.scalar(select(PhysicianAffiliation).where(
        PhysicianAffiliation.tenant_id == user.tenant_id,
        PhysicianAffiliation.physician_id == doctor.id,
        PhysicianAffiliation.hospital_id == hospital.id,
    ).with_for_update())
    if row and row.status == "locally_recorded":
        return {"hospital_id": hospital.id, "reused": True,
                "external_affiliation_verified": False}
    if row:
        row.status = "locally_recorded"
        row.recorded_by = user.id
    else:
        db.add(PhysicianAffiliation(
            tenant_id=user.tenant_id, physician_id=doctor.id,
            hospital_id=hospital.id, recorded_by=user.id,
            status="locally_recorded",
        ))
    event(db, user, "hospital_affiliation_recorded", "Physician", doctor.id)
    db.commit()
    return {"hospital_id": hospital.id, "reused": False,
            "external_affiliation_verified": False}


@router.post("/physicians/{physician_id}/affiliations/{hospital_id}/revoke")
def remove_affiliation(
    physician_id: str, hospital_id: str,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    directory_doctor(db, user, physician_id)
    row = db.scalar(select(PhysicianAffiliation).where(
        PhysicianAffiliation.tenant_id == user.tenant_id,
        PhysicianAffiliation.physician_id == physician_id,
        PhysicianAffiliation.hospital_id == hospital_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Affiliation not found")
    if row.status != "revoked":
        row.status = "revoked"
        event(db, user, "hospital_affiliation_revoked", "Physician", physician_id)
        db.commit()
    return {"active": False, "external_affiliation_verified": False}


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def requires_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone offset required")
        return value


@router.post("/physicians/{physician_id}/availability", status_code=201)
def propose_availability(
    physician_id: str, body: AvailabilityIn,
    db: Session = Depends(get_db), user: User = Depends(admin),
):
    doctor = directory_doctor(db, user, physician_id)
    start, end = utc(body.starts_at), utc(body.ends_at)
    if start < now() or end <= start or end - start > timedelta(hours=8) or start > now() + timedelta(days=365):
        raise HTTPException(422, "Availability must be a future 1-8 hour window within 365 days")
    db.scalar(select(Physician.id).where(
        Physician.id == doctor.id, Physician.tenant_id == user.tenant_id,
    ).with_for_update())
    overlaps = db.scalar(select(PhysicianAvailability).where(
        PhysicianAvailability.tenant_id == user.tenant_id,
        PhysicianAvailability.physician_id == doctor.id,
        PhysicianAvailability.status == "proposed",
        PhysicianAvailability.starts_at < end,
        PhysicianAvailability.ends_at > start,
    ).limit(1))
    if overlaps is not None:
        raise HTTPException(409, "Overlapping proposed slot")
    slot = PhysicianAvailability(
        tenant_id=user.tenant_id, physician_id=doctor.id,
        starts_at=start, ends_at=end, status="proposed", recorded_by=user.id,
    )
    db.add(slot)
    db.flush()
    event(db, user, "availability_proposed", "PhysicianAvailability", slot.id)
    db.commit()
    return {"id": slot.id, "status": "proposed", "externally_confirmed": False,
            "appointment_booked": False}


@router.post("/availability/{slot_id}/cancel")
def cancel_availability(
    slot_id: str, db: Session = Depends(get_db), user: User = Depends(admin),
):
    slot = db.scalar(select(PhysicianAvailability).where(
        PhysicianAvailability.id == slot_id,
        PhysicianAvailability.tenant_id == user.tenant_id,
    ).with_for_update())
    if slot is None:
        raise HTTPException(404, "Slot not found")
    if slot.status != "cancelled":
        slot.status = "cancelled"
        event(db, user, "availability_cancelled", "PhysicianAvailability", slot.id)
        db.commit()
    return {"id": slot.id, "status": "cancelled", "external_provider_notified": False}


def current_physician(db: Session, user: User) -> Physician:
    account = db.scalar(select(PhysicianAccount).where(
        PhysicianAccount.tenant_id == user.tenant_id,
        PhysicianAccount.user_id == user.id,
        PhysicianAccount.active.is_(True),
    ))
    if account is None:
        raise HTTPException(403, "Physician account is not linked or is revoked")
    doctor = directory_doctor(db, user, account.physician_id)
    evidence = credential_row(db, user.tenant_id, doctor.id)
    if evidence_state(evidence) != "locally_attested":
        raise HTTPException(403, "Current locally attested directory credential required")
    # The staff role itself still does not confer independent clinical privileges.
    return doctor


@router.get("/portal/me")
def my_profile(
    db: Session = Depends(get_db), user: User = Depends(physician),
):
    doctor = current_physician(db, user)
    return {**doctor_summary(db, doctor),
            "physician_user_id": user.id, "patient_identifiers_included": False}


@router.get("/portal/referrals")
def my_referrals(
    db: Session = Depends(get_db), user: User = Depends(physician),
    limit: int = Query(50, ge=1, le=100),
):
    doctor = current_physician(db, user)
    rows = db.scalars(select(Referral).where(
        Referral.tenant_id == user.tenant_id, Referral.physician_id == doctor.id,
    ).order_by(Referral.created_at.desc()).limit(limit)).all()
    return {
        "items": [{"id": x.id, "case_reference": x.case_id, "status": x.status,
                   "created_at": x.created_at} for x in rows],
        "raw_patient_data_included": False,
        "clinical_approval_possible": False,
    }


@router.get("/portal/appointments")
def my_appointments(
    db: Session = Depends(get_db), user: User = Depends(physician),
    limit: int = Query(50, ge=1, le=100),
):
    doctor = current_physician(db, user)
    rows = db.scalars(select(Appointment).where(
        Appointment.tenant_id == user.tenant_id, Appointment.physician_id == doctor.id,
    ).order_by(Appointment.requested_at.desc()).limit(limit)).all()
    return {
        "items": [{"id": x.id, "case_reference": x.case_id,
                   "requested_at": x.requested_at, "status": x.status}
                  for x in rows],
        "external_booking_verified": False,
        "medical_details_included": False,
    }


@router.get("/portal/availability")
def my_availability(
    db: Session = Depends(get_db), user: User = Depends(physician),
    limit: int = Query(50, ge=1, le=100),
):
    doctor = current_physician(db, user)
    rows = db.scalars(select(PhysicianAvailability).where(
        PhysicianAvailability.tenant_id == user.tenant_id,
        PhysicianAvailability.physician_id == doctor.id,
        PhysicianAvailability.status == "proposed",
    ).order_by(PhysicianAvailability.starts_at).limit(limit)).all()
    return {
        "items": [{"id": x.id, "starts_at": x.starts_at,
                   "ends_at": x.ends_at, "status": x.status} for x in rows],
        "externally_confirmed": False,
        "real_time_calendar_sync": False,
    }
