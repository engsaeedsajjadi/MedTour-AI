"""Section 17: metadata-only, human-controlled medical visa coordination.

This module never applies for, verifies, or grants a visa. Source references are
manual internal attestations only; passport numbers, scans, DOB and medical
narratives must never be entered here. The alpha runtime disallows real PHI.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Audit, Case, Patient, User
from .enterprise_models import CaseTimeline, MedicalVisa, MedicalVisaChecklist, MedicalVisaEvent
from .safety_rules import active_consent
from .security import roles

router = APIRouter(prefix="/api/v1/visa-coordination", tags=["medical visa coordination"])
staff = roles("admin", "operator")
admin = roles("admin")
REF = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
KEY = r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$"
CHECKS = ("identity_document", "provider_invitation", "travel_plan", "application_forms")
ACTIVE = ("requested", "in_review", "ready_for_manual_submission", "submission_reported")
OUTCOMES = ("issued_reported", "refused_reported", "additional_information_reported")


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def case_patient(db: Session, user: User, case_id: str, *, lock: bool = False):
    stmt = select(Case).where(Case.id == case_id, Case.tenant_id == user.tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    case = db.scalar(stmt)
    if not case:
        raise HTTPException(404, "Case not found")
    patient = db.scalar(select(Patient).where(
        Patient.id == case.patient_id, Patient.tenant_id == user.tenant_id))
    if not patient:
        raise HTTPException(404, "Patient not found")
    if not active_consent(db, user.tenant_id, patient.id, "intake"):
        raise HTTPException(409, "Active intake consent required")
    if not active_consent(db, user.tenant_id, patient.id, "visa_coordination"):
        raise HTTPException(409, "Specific visa coordination consent required")
    if case.status in ("closed", "cancelled"):
        raise HTTPException(409, "Inactive case")
    return case, patient


def application(db: Session, user: User, application_id: str, *, lock: bool = False):
    # Always lock Case before MedicalVisa, same lock order as creation.
    candidate = db.scalar(select(MedicalVisa).where(
        MedicalVisa.id == application_id, MedicalVisa.tenant_id == user.tenant_id))
    if candidate is None:
        raise HTTPException(404, "Visa coordination record not found")
    case, patient = case_patient(db, user, candidate.case_id, lock=lock)
    stmt = select(MedicalVisa).where(
        MedicalVisa.id == application_id, MedicalVisa.tenant_id == user.tenant_id,
        MedicalVisa.case_id == case.id, MedicalVisa.patient_id == patient.id)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Visa coordination record not found")
    if row.status == "blocked":
        raise HTTPException(409, "Withdrawn consent permanently blocks this record; create a new request")
    return case, patient, row


def checklist(db: Session, user: User, row: MedicalVisa):
    return db.scalars(select(MedicalVisaChecklist).where(
        MedicalVisaChecklist.tenant_id == user.tenant_id,
        MedicalVisaChecklist.application_id == row.id,
    ).order_by(MedicalVisaChecklist.item_key)).all()


def view(row: MedicalVisa, checks: list[MedicalVisaChecklist]):
    return {
        "id": row.id, "case_id": row.case_id, "patient_id": row.patient_id,
        "origin_country": row.origin_country, "destination_country": row.destination_country,
        "visa_type": row.visa_type, "intended_departure_at": row.intended_departure_at,
        "status": row.status, "next_action_due_at": row.next_action_due_at,
        "authority_name": row.authority_name, "external_reference": row.external_reference,
        "decision_reported": row.decision_reported, "created_at": row.created_at,
        "checklist": [{"item_key": c.item_key, "status": c.status,
                       "review_reference": c.review_reference, "reviewed_at": c.reviewed_at}
                      for c in checks],
        "official_visa_issued_verified": False, "government_integration_live": False,
        "external_submission_verified": False, "internal_coordination_only": True,
        "requirements_officially_validated": False,
    }


class CreateVisa(BaseModel):
    request_key: str = Field(min_length=8, max_length=100, pattern=KEY)
    origin_country: str = Field(pattern=r"^[A-Z]{2}$")
    destination_country: Literal["IR"] = "IR"
    visa_type: Literal["medical"] = "medical"
    intended_departure_at: datetime | None = None
    next_action_due_at: datetime | None = None

    @field_validator("intended_departure_at", "next_action_due_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timezone offset is required")
        return value


@router.post("/cases/{case_id}/applications", status_code=201)
def create(case_id: str, body: CreateVisa,
           db: Session = Depends(get_db), user: User = Depends(staff)):
    now = datetime.now(timezone.utc)
    if body.intended_departure_at is not None and not (
        now < utc(body.intended_departure_at) <= now + timedelta(days=730)
    ):
        raise HTTPException(422, "Departure must be within the next two years")
    if body.next_action_due_at is not None and not (
        now < utc(body.next_action_due_at) <= now + timedelta(days=365)
    ):
        raise HTTPException(422, "Next action must be within the next year")
    case, patient = case_patient(db, user, case_id, lock=True)
    old = db.scalar(select(MedicalVisa).where(
        MedicalVisa.tenant_id == user.tenant_id, MedicalVisa.case_id == case.id,
        MedicalVisa.request_key == body.request_key))
    if old is not None:
        if (old.origin_country != body.origin_country
                or old.destination_country != body.destination_country
                or old.visa_type != body.visa_type
                or old.intended_departure_at != (utc(body.intended_departure_at) if body.intended_departure_at else None)
                or old.next_action_due_at != (utc(body.next_action_due_at) if body.next_action_due_at else None)):
            raise HTTPException(409, "Idempotency key conflict")
        if old.status == "blocked":
            raise HTTPException(409, "Old record blocked on consent withdrawal")
        return {**view(old, checklist(db, user, old)), "reused": True}
    row = MedicalVisa(
        tenant_id=user.tenant_id, case_id=case.id, patient_id=patient.id,
        origin_country=body.origin_country, destination_country=body.destination_country,
        visa_type=body.visa_type, request_key=body.request_key,
        intended_departure_at=utc(body.intended_departure_at) if body.intended_departure_at else None,
        next_action_due_at=utc(body.next_action_due_at) if body.next_action_due_at else None,
        created_by=user.id, status="requested",
    )
    db.add(row)
    db.flush()
    for item in CHECKS:
        db.add(MedicalVisaChecklist(
            tenant_id=user.tenant_id, application_id=row.id, item_key=item,
            status="pending"))
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id, event="visa_record_created",
                 entity_type="MedicalVisa", entity_id=row.id))
    db.add(CaseTimeline(tenant_id=user.tenant_id, case_id=case.id, actor_id=user.id,
                        event="visa_record_created", details="visa=" + row.id + ";manual_only"))
    db.commit()
    return {**view(row, checklist(db, user, row)), "reused": False}


@router.get("/cases/{case_id}/applications")
def by_case(case_id: str, db: Session = Depends(get_db), user: User = Depends(staff)):
    case, patient = case_patient(db, user, case_id)
    rows = db.scalars(select(MedicalVisa).where(
        MedicalVisa.tenant_id == user.tenant_id, MedicalVisa.case_id == case.id,
        MedicalVisa.patient_id == patient.id).order_by(
            MedicalVisa.created_at.desc(), MedicalVisa.id.desc()).limit(100)).all()
    return {"items": [view(row, checklist(db, user, row)) for row in rows],
            "official_visa_decisions_connected": False}


@router.get("/due")
def due(limit: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db), user: User = Depends(staff)):
    # Metadata-only staff action queue; do not expose passport/clinical data.
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(MedicalVisa).join(
        Case, Case.id == MedicalVisa.case_id).where(
        MedicalVisa.tenant_id == user.tenant_id, Case.tenant_id == user.tenant_id,
        MedicalVisa.status.in_(ACTIVE), MedicalVisa.next_action_due_at.is_not(None),
        MedicalVisa.next_action_due_at <= now).order_by(
            MedicalVisa.next_action_due_at.asc()).limit(limit)).all()
    items = []
    for row in rows:
        if (active_consent(db, user.tenant_id, row.patient_id, "intake")
                and active_consent(db, user.tenant_id, row.patient_id, "visa_coordination")):
            items.append({"id": row.id, "case_id": row.case_id,
                          "status": row.status, "next_action_due_at": row.next_action_due_at})
    return {"items": items, "automatic_notifications_sent": False}


class ChecklistIn(BaseModel):
    item_key: Literal["identity_document", "provider_invitation", "travel_plan", "application_forms"]
    status: Literal["received", "needs_update", "locally_reviewed"]
    review_reference: str | None = Field(default=None, min_length=6, max_length=100, pattern=REF)


@router.post("/applications/{application_id}/checklist")
def review_check(application_id: str, body: ChecklistIn,
                 db: Session = Depends(get_db), user: User = Depends(staff)):
    case, patient, row = application(db, user, application_id, lock=True)
    if row.status not in ("requested", "in_review"):
        raise HTTPException(409, "Checklist is frozen after internal readiness review")
    if body.status == "locally_reviewed" and user.role != "admin":
        raise HTTPException(403, "Local document review requires administrator")
    if body.status == "locally_reviewed" and not body.review_reference:
        raise HTTPException(422, "Review reference required")
    item = db.scalar(select(MedicalVisaChecklist).where(
        MedicalVisaChecklist.tenant_id == user.tenant_id,
        MedicalVisaChecklist.application_id == row.id,
        MedicalVisaChecklist.item_key == body.item_key).with_for_update())
    if item is None:
        raise HTTPException(404, "Checklist item not found")
    # A checklist reference is an internal opaque identifier, never a passport number.
    if (item.status == body.status and item.review_reference == body.review_reference):
        return {**view(row, checklist(db, user, row)), "reused": True}
    item.status = body.status
    item.review_reference = body.review_reference if body.status == "locally_reviewed" else None
    item.reviewed_by = user.id if body.status == "locally_reviewed" else None
    item.reviewed_at = datetime.now(timezone.utc) if body.status == "locally_reviewed" else None
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id, event="visa_checklist_" + body.status,
                 entity_type="MedicalVisaChecklist", entity_id=item.id))
    db.commit()
    return {**view(row, checklist(db, user, row)), "reused": False}


class StepIn(BaseModel):
    step_key: str = Field(min_length=8, max_length=100, pattern=KEY)
    action: Literal["start_review", "ready_for_manual_submission", "record_submission",
                    "record_outcome", "cancel"]
    reference: str = Field(min_length=6, max_length=100, pattern=REF)
    authority_name: str | None = Field(default=None, min_length=6, max_length=100,
                                       pattern=r"^[A-Za-z][A-Za-z0-9 ._/-]{5,99}$")
    outcome: Literal["issued_reported", "refused_reported", "additional_information_reported"] | None = None
    next_action_due_at: datetime | None = None

    @field_validator("next_action_due_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timezone offset required")
        return value


def fingerprint(body: StepIn) -> str:
    return hashlib.sha256(body.model_dump_json(exclude_none=False).encode()).hexdigest()


@router.post("/applications/{application_id}/transition")
def transition(application_id: str, body: StepIn,
               db: Session = Depends(get_db), user: User = Depends(staff)):
    case, patient, row = application(db, user, application_id, lock=True)
    if body.next_action_due_at and not (
        datetime.now(timezone.utc) < utc(body.next_action_due_at)
        <= datetime.now(timezone.utc) + timedelta(days=365)
    ):
        raise HTTPException(422, "Next action date is invalid")
    digest = fingerprint(body)
    previous = db.scalar(select(MedicalVisaEvent).where(
        MedicalVisaEvent.tenant_id == user.tenant_id,
        MedicalVisaEvent.application_id == row.id,
        MedicalVisaEvent.step_key == body.step_key))
    if previous:
        if previous.fingerprint != digest:
            raise HTTPException(409, "Idempotency key conflict")
        return {**view(row, checklist(db, user, row)), "reused": True}
    allowed = {
        "start_review": ("requested",),
        "ready_for_manual_submission": ("in_review",),
        "record_submission": ("ready_for_manual_submission",),
        "record_outcome": ("submission_reported",),
        "cancel": ACTIVE,
    }
    if row.status not in allowed[body.action]:
        raise HTTPException(409, "Invalid visa coordination transition")
    if body.action != "start_review" and user.role != "admin":
        raise HTTPException(403, "Administrator human review required")
    if body.action in ("record_submission", "record_outcome") and not body.authority_name:
        raise HTTPException(422, "Authority name required for manually reported external stage")
    if body.action == "record_outcome" and body.outcome not in OUTCOMES:
        raise HTTPException(422, "Reported outcome is required")
    if body.action != "record_outcome" and body.outcome is not None:
        raise HTTPException(422, "Unexpected reported outcome")
    if body.action == "ready_for_manual_submission":
        checks = checklist(db, user, row)
        if len(checks) != len(CHECKS) or any(
            c.status != "locally_reviewed" or not c.review_reference for c in checks
        ):
            raise HTTPException(409, "All local administrative checklist reviews are required")
    before = row.status
    if body.action == "start_review":
        row.status = "in_review"
    elif body.action == "ready_for_manual_submission":
        row.status = "ready_for_manual_submission"
    elif body.action == "record_submission":
        row.status = "submission_reported"
        row.authority_name = body.authority_name
        row.external_reference = body.reference
    elif body.action == "record_outcome":
        row.decision_reported = body.outcome
        row.status = ("in_review" if body.outcome == "additional_information_reported"
                      else "outcome_reported")
        row.authority_name = body.authority_name
    else:
        row.status = "cancelled"
    if body.next_action_due_at is not None:
        row.next_action_due_at = utc(body.next_action_due_at)
    row.reviewed_by = user.id
    db.add(MedicalVisaEvent(
        tenant_id=user.tenant_id, application_id=row.id, actor_id=user.id,
        step_key=body.step_key, fingerprint=digest, action=body.action,
        old_status=before, new_status=row.status,
        reference=body.reference, occurred_at=datetime.now(timezone.utc),
    ))
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id,
                 event="visa_" + body.action, entity_type="MedicalVisa", entity_id=row.id))
    db.add(CaseTimeline(tenant_id=user.tenant_id, case_id=case.id,
                        actor_id=user.id, event="visa_" + body.action,
                        details="visa=" + row.id + ";manual_record_only"))
    db.commit()
    return {**view(row, checklist(db, user, row)), "reused": False}


@router.get("/applications/{application_id}/history")
def history(application_id: str,
            db: Session = Depends(get_db), user: User = Depends(staff)):
    case, patient, row = application(db, user, application_id)
    events = db.scalars(select(MedicalVisaEvent).where(
        MedicalVisaEvent.tenant_id == user.tenant_id,
        MedicalVisaEvent.application_id == row.id).order_by(
            MedicalVisaEvent.occurred_at, MedicalVisaEvent.id).limit(100)).all()
    return {"items": [
        {"id": x.id, "action": x.action, "previous": x.old_status,
         "current": x.new_status, "reference": x.reference,
         "actor_id": x.actor_id, "at": x.occurred_at}
        for x in events], "independent_authority_verification": False}
