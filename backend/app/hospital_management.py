"""Section 13: hospital administrative coordination, synthetic Alpha.

A locally attested record does NOT verify hospital licensure, services,
staff employment, clinical capacity or an external booking. The hospital
portal exposes only assigned coordination references, never medical notes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Audit, Case, Hospital, Patient, User
from .enterprise_models import (
    HospitalAccount, HospitalCredential, HospitalService,
    HospitalCapacity, HospitalCoordination, CaseTimeline,
)
from .security import roles
from .safety_rules import active_consent

router = APIRouter(prefix="/api/v1/hospital-management", tags=["hospital management"])
admin = roles("admin")
staff = roles("admin", "operator")
hospital_staff = roles("hospital")
REF = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
SERVICES = frozenset({
    "cardiology", "oncology", "orthopedics", "ophthalmology",
    "dentistry", "neurosurgery", "diagnostics", "rehabilitation",
    "hospital_admission", "other",
})


def now():
    return datetime.now(timezone.utc)


def utc(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def owned_hospital(db: Session, user: User, hospital_id: str):
    row = db.scalar(select(Hospital).where(
        Hospital.id == hospital_id, Hospital.tenant_id == user.tenant_id,
    ))
    if row is None:
        raise HTTPException(404, "Hospital not found")
    return row


def log(db: Session, actor: User, event: str, entity_id: str, kind: str = "Hospital"):
    db.add(Audit(
        tenant_id=actor.tenant_id, user_id=actor.id,
        event="hospital_" + event, entity_type=kind, entity_id=entity_id,
    ))


def credential(db: Session, tenant: str, hid: str):
    return db.scalar(select(HospitalCredential).where(
        HospitalCredential.tenant_id == tenant, HospitalCredential.hospital_id == hid,
    ))


def evidence_state(row):
    if row is None: return "missing"
    if row.status != "locally_attested": return "revoked"
    return "locally_attested" if utc(row.expires_at) > now() else "expired"


def hospital_view(db: Session, row: Hospital):
    evidence = credential(db, row.tenant_id, row.id)
    accounts = db.scalars(select(HospitalAccount).where(
        HospitalAccount.tenant_id == row.tenant_id,
        HospitalAccount.hospital_id == row.id, HospitalAccount.active.is_(True),
    ).limit(50)).all()
    services = db.scalars(select(HospitalService).where(
        HospitalService.tenant_id == row.tenant_id,
        HospitalService.hospital_id == row.id,
        HospitalService.status == "locally_recorded",
    ).limit(30)).all()
    return {
        "hospital_id": row.id, "name": row.name, "city": row.city,
        "legacy_directory_status": row.license_status,
        "evidence_status": evidence_state(evidence),
        "evidence_expiry": evidence.expires_at if evidence else None,
        "linked_user_ids": [x.user_id for x in accounts],
        "service_codes": [x.service_code for x in services],
        "regulator_license_verified": False,
        "hospital_services_externally_verified": False,
        "hospital_capacity_live_verified": False,
        "patient_data_included": False,
    }


@router.get("/directory")
def directory(limit: int = Query(100, ge=1, le=100),
              db: Session = Depends(get_db), user: User = Depends(staff)):
    rows = db.scalars(select(Hospital).where(
        Hospital.tenant_id == user.tenant_id,
    ).order_by(Hospital.created_at.desc()).limit(limit)).all()
    return {"items": [hospital_view(db, row) for row in rows], "bounded": True,
            "regulator_license_verified": False, "real_patient_data_allowed": False}


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str


@router.put("/hospitals/{hospital_id}/accounts")
def link_account(hospital_id: str, body: LinkIn,
                 db: Session = Depends(get_db), user: User = Depends(admin)):
    owned_hospital(db, user, hospital_id)
    target = db.scalar(select(User).where(
        User.tenant_id == user.tenant_id, User.id == body.user_id,
        User.role == "hospital", User.active.is_(True),
    ).with_for_update())
    if target is None:
        raise HTTPException(404, "Active hospital staff account not found")
    existing = db.scalar(select(HospitalAccount).where(
        HospitalAccount.tenant_id == user.tenant_id,
        HospitalAccount.user_id == target.id,
    ).with_for_update())
    if existing and existing.hospital_id != hospital_id:
        raise HTTPException(409, "Hospital account already linked elsewhere")
    if existing and existing.active:
        return {"hospital_id": hospital_id, "user_id": target.id,
                "reused": True, "independent_staff_identity_verified": False}
    if existing:
        existing.active = True
        existing.linked_by = user.id
    else:
        db.add(HospitalAccount(tenant_id=user.tenant_id, hospital_id=hospital_id,
                               user_id=target.id, linked_by=user.id, active=True))
    log(db, user, "account_linked", hospital_id)
    db.commit()
    return {"hospital_id": hospital_id, "user_id": target.id,
            "reused": False, "independent_staff_identity_verified": False}


@router.post("/hospitals/{hospital_id}/accounts/{user_id}/revoke")
def unlink_account(hospital_id: str, user_id: str,
                   db: Session = Depends(get_db), user: User = Depends(admin)):
    owned_hospital(db, user, hospital_id)
    row = db.scalar(select(HospitalAccount).where(
        HospitalAccount.tenant_id == user.tenant_id,
        HospitalAccount.hospital_id == hospital_id,
        HospitalAccount.user_id == user_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Linked account not found")
    if row.active:
        row.active = False
        log(db, user, "account_revoked", hospital_id)
        db.commit()
    return {"hospital_id": hospital_id, "user_id": user_id, "portal_access": False}


class CredentialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuing_country: str = Field(pattern=r"^[A-Z]{2}$")
    issuing_authority: str = Field(min_length=3, max_length=120)
    registration_reference: str = Field(min_length=6, max_length=100, pattern=REF)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("Timezone-aware expiry required")
        value = value.astimezone(timezone.utc)
        if not now()+timedelta(days=1) <= value <= now()+timedelta(days=1095):
            raise ValueError("Expiry must be 1-1095 days in the future")
        return value


@router.put("/hospitals/{hospital_id}/credential")
def attest_credential(hospital_id: str, body: CredentialIn,
                      db: Session = Depends(get_db), user: User = Depends(admin)):
    owned_hospital(db, user, hospital_id)
    row = db.scalar(select(HospitalCredential).where(
        HospitalCredential.tenant_id == user.tenant_id,
        HospitalCredential.hospital_id == hospital_id,
    ).with_for_update())
    if row is None:
        row = HospitalCredential(tenant_id=user.tenant_id, hospital_id=hospital_id,
                                 checked_by=user.id)
        db.add(row)
    row.issuing_country = body.issuing_country
    row.issuing_authority = body.issuing_authority
    row.registration_reference = body.registration_reference
    row.status = "locally_attested"
    row.checked_by = user.id
    row.checked_at = now()
    row.expires_at = body.expires_at
    log(db, user, "evidence_locally_attested", hospital_id)
    db.commit()
    return {"hospital_id": hospital_id, "status": row.status,
            "regulator_license_verified": False, "clinical_booking_authorized": False}


@router.post("/hospitals/{hospital_id}/credential/revoke")
def revoke_credential(hospital_id: str, db: Session = Depends(get_db),
                      user: User = Depends(admin)):
    owned_hospital(db, user, hospital_id)
    row = db.scalar(select(HospitalCredential).where(
        HospitalCredential.tenant_id == user.tenant_id,
        HospitalCredential.hospital_id == hospital_id,
    ).with_for_update())
    if row is None: raise HTTPException(404, "Hospital evidence not found")
    if row.status != "revoked":
        row.status = "revoked"
        log(db, user, "evidence_revoked", hospital_id)
        db.commit()
    return {"hospital_id": hospital_id, "portal_access": False,
            "regulator_license_verified": False}


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_code: Literal[
        "cardiology","oncology","orthopedics","ophthalmology","dentistry",
        "neurosurgery","diagnostics","rehabilitation","hospital_admission","other",
    ]


@router.post("/hospitals/{hospital_id}/services")
def record_service(hospital_id: str, body: ServiceIn,
                   db: Session = Depends(get_db), user: User = Depends(admin)):
    owned_hospital(db, user, hospital_id)
    row = db.scalar(select(HospitalService).where(
        HospitalService.tenant_id == user.tenant_id,
        HospitalService.hospital_id == hospital_id,
        HospitalService.service_code == body.service_code,
    ).with_for_update())
    if row and row.status == "locally_recorded":
        return {"service_code": row.service_code, "reused": True,
                "hospital_service_externally_verified": False}
    if row:
        row.status = "locally_recorded"
        row.recorded_by = user.id
    else:
        db.add(HospitalService(tenant_id=user.tenant_id,
             hospital_id=hospital_id, service_code=body.service_code,
             status="locally_recorded", recorded_by=user.id))
    log(db, user, "service_recorded", hospital_id)
    db.commit()
    return {"service_code": body.service_code, "reused": False,
            "hospital_service_externally_verified": False}


@router.post("/hospitals/{hospital_id}/services/{code}/revoke")
def revoke_service(hospital_id: str, code: str,
                   db: Session = Depends(get_db), user: User = Depends(admin)):
    owned_hospital(db, user, hospital_id)
    row = db.scalar(select(HospitalService).where(
        HospitalService.tenant_id == user.tenant_id,
        HospitalService.hospital_id == hospital_id,
        HospitalService.service_code == code,
    ).with_for_update())
    if row is None: raise HTTPException(404, "Hospital service not found")
    if row.status != "revoked":
        row.status = "revoked"
        log(db, user, "service_revoked", hospital_id)
        db.commit()
    return {"service_code": code, "active": False}


class CapacityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_code: Literal[
        "cardiology","oncology","orthopedics","ophthalmology","dentistry",
        "neurosurgery","diagnostics","rehabilitation","hospital_admission","other",
    ]
    starts_at: datetime
    ends_at: datetime
    proposed_units: int = Field(ge=1, le=100)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def tz_required(cls, value: datetime):
        if value.tzinfo is None: raise ValueError("UTC offset required")
        return value


@router.post("/hospitals/{hospital_id}/capacity", status_code=201)
def propose_capacity(hospital_id: str, body: CapacityIn,
                     db: Session = Depends(get_db), user: User = Depends(admin)):
    hospital = owned_hospital(db, user, hospital_id)
    start, end = utc(body.starts_at), utc(body.ends_at)
    if start < now() or end <= start or end - start > timedelta(days=1) or start > now()+timedelta(days=365):
        raise HTTPException(422, "Proposed capacity must be future <=24 hours within 365 days")
    db.scalar(select(Hospital.id).where(
        Hospital.id == hospital.id, Hospital.tenant_id == user.tenant_id,
    ).with_for_update())
    service = db.scalar(select(HospitalService).where(
        HospitalService.tenant_id == user.tenant_id,
        HospitalService.hospital_id == hospital.id,
        HospitalService.service_code == body.service_code,
        HospitalService.status == "locally_recorded",
    ))
    if service is None: raise HTTPException(409, "Service is not registered")
    overlap = db.scalar(select(HospitalCapacity).where(
        HospitalCapacity.tenant_id == user.tenant_id,
        HospitalCapacity.hospital_id == hospital.id,
        HospitalCapacity.service_code == body.service_code,
        HospitalCapacity.status == "proposed",
        HospitalCapacity.starts_at < end,
        HospitalCapacity.ends_at > start,
    ).limit(1))
    if overlap: raise HTTPException(409, "Proposed capacity overlaps")
    row = HospitalCapacity(tenant_id=user.tenant_id, hospital_id=hospital.id,
         service_code=body.service_code, starts_at=start, ends_at=end,
         proposed_units=body.proposed_units, status="proposed", recorded_by=user.id)
    db.add(row)
    db.flush()
    log(db, user, "capacity_proposed", row.id, kind="HospitalCapacity")
    db.commit()
    return {"id": row.id, "status": row.status,
            "live_capacity_verified": False, "external_booking_created": False}


@router.post("/capacity/{slot_id}/cancel")
def cancel_capacity(slot_id: str, db: Session = Depends(get_db),
                    user: User = Depends(admin)):
    row = db.scalar(select(HospitalCapacity).where(
        HospitalCapacity.id == slot_id, HospitalCapacity.tenant_id == user.tenant_id,
    ).with_for_update())
    if row is None: raise HTTPException(404, "Capacity window not found")
    if row.status != "cancelled":
        row.status = "cancelled"
        log(db, user, "capacity_cancelled", row.id, kind="HospitalCapacity")
        db.commit()
    return {"id": row.id, "status": row.status, "external_provider_notified": False}


def current_hospital(db: Session, user: User):
    account = db.scalar(select(HospitalAccount).where(
        HospitalAccount.tenant_id == user.tenant_id,
        HospitalAccount.user_id == user.id, HospitalAccount.active.is_(True),
    ))
    if account is None:
        raise HTTPException(403, "Hospital staff account is not linked")
    hospital = owned_hospital(db, user, account.hospital_id)
    if evidence_state(credential(db, user.tenant_id, hospital.id)) != "locally_attested":
        raise HTTPException(403, "Current locally attested hospital evidence required")
    return hospital


@router.get("/portal/me")
def hospital_profile(db: Session = Depends(get_db),
                     user: User = Depends(hospital_staff)):
    hospital = current_hospital(db, user)
    return {**hospital_view(db, hospital), "hospital_user_id": user.id,
            "patient_identifiers_included": False, "clinical_approval_possible": False}


@router.get("/portal/capacity")
def my_capacity(limit: int = Query(50, ge=1, le=100),
                db: Session = Depends(get_db), user: User = Depends(hospital_staff)):
    hospital = current_hospital(db, user)
    rows = db.scalars(select(HospitalCapacity).where(
        HospitalCapacity.tenant_id == user.tenant_id,
        HospitalCapacity.hospital_id == hospital.id,
        HospitalCapacity.status == "proposed",
    ).order_by(HospitalCapacity.starts_at).limit(limit)).all()
    return {"items": [{"id":r.id, "service_code":r.service_code,
                       "starts_at":r.starts_at, "ends_at":r.ends_at,
                       "proposed_units":r.proposed_units, "status":r.status}
                      for r in rows],
            "real_time_verified":False, "reservable":False}


class CoordinationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    service_code: Literal[
        "cardiology","oncology","orthopedics","ophthalmology","dentistry",
        "neurosurgery","diagnostics","rehabilitation","hospital_admission","other",
    ]
    reference: str = Field(min_length=6,max_length=100,pattern=REF)


@router.post("/hospitals/{hospital_id}/coordinations", status_code=201)
def create_coordination(hospital_id: str, body: CoordinationIn,
                        db: Session = Depends(get_db), user: User = Depends(admin)):
    hospital = owned_hospital(db, user, hospital_id)
    case = db.scalar(select(Case).where(
        Case.id == body.case_id, Case.tenant_id == user.tenant_id,
    ).with_for_update())
    if case is None: raise HTTPException(404, "Case not found")
    patient = db.scalar(select(Patient).where(
        Patient.id == case.patient_id, Patient.tenant_id == user.tenant_id,
    ))
    if patient is None: raise HTTPException(404, "Patient not found")
    if not active_consent(db, user.tenant_id, patient.id, "intake"):
        raise HTTPException(409, "Current intake consent required")
    if not active_consent(db, user.tenant_id, patient.id, "hospital_coordination"):
        raise HTTPException(409, "Explicit hospital coordination consent required")
    if evidence_state(credential(db, user.tenant_id, hospital.id)) != "locally_attested":
        raise HTTPException(409, "Local hospital credential evidence is not current")
    service = db.scalar(select(HospitalService).where(
        HospitalService.tenant_id == user.tenant_id, HospitalService.hospital_id == hospital.id,
        HospitalService.service_code == body.service_code,
        HospitalService.status == "locally_recorded",
    ))
    if not service: raise HTTPException(409, "Hospital service not recorded")
    previous = db.scalar(select(HospitalCoordination).where(
        HospitalCoordination.tenant_id == user.tenant_id,
        HospitalCoordination.hospital_id == hospital.id,
        HospitalCoordination.case_id == case.id,
        HospitalCoordination.reference == body.reference,
    ))
    if previous:
        if previous.service_code != body.service_code:
            raise HTTPException(409, "Reference already used for different service")
        return {"id":previous.id, "status":previous.status, "reused":True,
                "booking_confirmed":False, "external_message_sent":False}
    row = HospitalCoordination(tenant_id=user.tenant_id, hospital_id=hospital.id,
         patient_id=patient.id, case_id=case.id, service_code=body.service_code,
         reference=body.reference, status="requested", recorded_by=user.id)
    db.add(row)
    db.flush()
    log(db,user,"coordination_requested",row.id,"HospitalCoordination")
    db.add(CaseTimeline(tenant_id=user.tenant_id, case_id=case.id,actor_id=user.id,
                        event="hospital_coordination_requested",
                        details=f"hospital={hospital.id};request={row.id};service={body.service_code}"))
    db.commit()
    return {"id":row.id,"status":"requested","reused":False,
            "booking_confirmed":False,"external_message_sent":False}


def coordination_view(row: HospitalCoordination):
    return {"id":row.id,"hospital_id":row.hospital_id,"case_reference":row.case_id,
            "service_code":row.service_code,"status":row.status,
            "created_at":row.created_at,"booking_confirmed":False,
            "real_patient_data_included":False}


@router.get("/portal/coordinations")
def my_coordinations(limit:int=Query(50,ge=1,le=100),
                     db:Session=Depends(get_db),
                     user:User=Depends(hospital_staff)):
    hospital = current_hospital(db,user)
    rows = db.scalars(select(HospitalCoordination).where(
        HospitalCoordination.tenant_id == user.tenant_id,
        HospitalCoordination.hospital_id == hospital.id,
    ).order_by(HospitalCoordination.created_at.desc()).limit(limit)).all()
    return {"items":[coordination_view(r) for r in rows
            if r.status in ("requested","received")
            and active_consent(db,user.tenant_id,r.patient_id,"intake")
            and active_consent(db,user.tenant_id,r.patient_id,"hospital_coordination")],
            "raw_medical_data_included":False,"externally_delivered":False}


@router.post("/portal/coordinations/{coordination_id}/acknowledge")
def acknowledge(coordination_id:str,db:Session=Depends(get_db),
                user:User=Depends(hospital_staff)):
    hospital=current_hospital(db,user)
    row=db.scalar(select(HospitalCoordination).where(
        HospitalCoordination.id==coordination_id,
        HospitalCoordination.tenant_id==user.tenant_id,
        HospitalCoordination.hospital_id==hospital.id,
    ).with_for_update())
    if row is None: raise HTTPException(404, "Coordination not found")
    if row.status!="requested":
        raise HTTPException(409,"Request cannot be acknowledged")
    if not active_consent(db,user.tenant_id,row.patient_id,"intake"):
        raise HTTPException(409,"Current intake consent required")
    if not active_consent(db,user.tenant_id,row.patient_id,"hospital_coordination"):
        raise HTTPException(409,"Current hospital coordination consent required")
    row.status="received"
    row.last_actor_id=user.id
    log(db,user,"coordination_received",row.id,"HospitalCoordination")
    db.commit()
    return {"id":row.id,"status":"received","external_delivery_confirmed":False,
            "hospital_booking_confirmed":False,"clinical_approval":False}


@router.post("/hospitals/{hospital_id}/coordinations/{coordination_id}/cancel")
def cancel_coordination(hospital_id:str,coordination_id:str,
                        db:Session=Depends(get_db),user:User=Depends(admin)):
    owned_hospital(db,user,hospital_id)
    row=db.scalar(select(HospitalCoordination).where(
        HospitalCoordination.id==coordination_id,
        HospitalCoordination.tenant_id==user.tenant_id,
        HospitalCoordination.hospital_id==hospital_id,
    ).with_for_update())
    if row is None: raise HTTPException(404, "Coordination not found")
    if row.status != "cancelled":
        row.status="cancelled"
        row.last_actor_id=user.id
        log(db,user,"coordination_cancelled",row.id,"HospitalCoordination")
        db.commit()
    return {"id":row.id,"status":"cancelled","external_provider_notified":False}
