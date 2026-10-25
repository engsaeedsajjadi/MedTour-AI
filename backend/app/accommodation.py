"""Section 18: consent-gated, tenant-isolated administrative accommodation.

Inventory is a local proposed capacity declaration, NOT hotel stock. Neither an
internal hold nor manually reported supplier confirmation verifies a booking.
No passport numbers, clinical information, or guest personal data stored.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .enterprise_models import (AccommodationProperty, AccommodationInventory,
    AccommodationStay, AccommodationEvent, CaseTimeline)
from .models import Audit, Case, Patient, User
from .safety_rules import active_consent
from .security import roles

router = APIRouter(prefix="/api/v1/accommodation", tags=["internal accommodation coordination"])
staff = roles("admin", "operator")
admin = roles("admin")
REF = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
KEY = r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$"
ROOMS = ("single", "double", "accessible")
HELD = ("internally_held", "external_request_reported", "external_confirmation_reported")
ACTIVE = ("requested", *HELD)
CONFIRMATION = ("external_confirmation_reported", "external_decline_reported")


def authorized_case(db: Session, user: User, case_id: str, *, lock: bool = False):
    stmt = select(Case).where(Case.tenant_id == user.tenant_id, Case.id == case_id)
    case = db.scalar(stmt.with_for_update() if lock else stmt)
    if case is None:
        raise HTTPException(404, "Case not found")
    patient = db.scalar(select(Patient).where(
        Patient.tenant_id == user.tenant_id, Patient.id == case.patient_id))
    if patient is None:
        raise HTTPException(404, "Patient not found")
    if not active_consent(db, user.tenant_id, patient.id, "intake"):
        raise HTTPException(409, "Active intake consent required")
    if not active_consent(db, user.tenant_id, patient.id, "accommodation_coordination"):
        raise HTTPException(409, "Specific accommodation coordination consent required")
    if case.status in ("closed", "cancelled"):
        raise HTTPException(409, "Inactive case")
    return case, patient


def property_row(db: Session, user: User, property_id: str, *, lock: bool = False):
    stmt = select(AccommodationProperty).where(
        AccommodationProperty.tenant_id == user.tenant_id,
        AccommodationProperty.id == property_id)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Property not found")
    return row


def stay_row(db: Session, user: User, stay_id: str, *, lock: bool = False):
    # Shared lock ordering for create/hold/review: case -> property -> stay.
    first = db.scalar(select(AccommodationStay).where(
        AccommodationStay.tenant_id == user.tenant_id, AccommodationStay.id == stay_id))
    if first is None:
        raise HTTPException(404, "Stay not found")
    case, patient = authorized_case(db, user, first.case_id, lock=lock)
    location = property_row(db, user, first.property_id, lock=lock)
    stmt = select(AccommodationStay).where(
        AccommodationStay.tenant_id == user.tenant_id,
        AccommodationStay.id == stay_id, AccommodationStay.case_id == case.id,
        AccommodationStay.patient_id == patient.id, AccommodationStay.property_id == location.id)
    stay = db.scalar(stmt.with_for_update() if lock else stmt)
    if stay is None:
        raise HTTPException(404, "Stay not found")
    if stay.status == "blocked":
        raise HTTPException(409, "Old stay blocked by withdrawn consent; create a new request")
    return case, patient, location, stay


def current_window(start: date, end: date):
    today = datetime.now(timezone.utc).date()
    if not (today <= start <= today + timedelta(days=365)):
        raise HTTPException(422, "Arrival outside allowed planning window")
    if not (start < end <= start + timedelta(days=90)):
        raise HTTPException(422, "Stay must be 1 to 90 nights")


def property_view(p):
    return {"id": p.id, "name": p.name, "city": p.city,
            "status": p.status, "created_at": p.created_at,
            "independently_verified": False, "external_hotel_connected": False}


def inventory_view(i):
    return {"id": i.id, "property_id": i.property_id, "room_type": i.room_type,
            "starts_on": i.starts_on, "ends_on": i.ends_on,
            "proposed_rooms": i.proposed_rooms, "status": i.status,
            "reference": i.reference, "live_stock_verified": False}


def stay_view(s):
    return {"id": s.id, "case_id": s.case_id, "property_id": s.property_id,
            "patient_id": s.patient_id, "room_type": s.room_type,
            "starts_on": s.starts_on, "ends_on": s.ends_on,
            "rooms_requested": s.rooms_requested, "guests": s.guests,
            "status": s.status, "inventory_id": s.inventory_id,
            "internal_reference": s.internal_reference,
            "supplier_name": s.supplier_name, "supplier_reference": s.supplier_reference,
            "created_at": s.created_at,
            "provider_booking_independently_verified": False,
            "live_inventory_verified": False, "payment_collected": False,
            "human_coordination_only": True}


def audit(db, user, entity, event):
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id,
                 entity_type=type(entity).__name__, entity_id=entity.id, event=event))


class PropertyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=150, pattern=r"^[^\x00-\x1F\x7F]+$")
    city: str = Field(min_length=2, max_length=80, pattern=r"^[^\x00-\x1F\x7F]+$")


@router.post("/properties", status_code=201)
def create_property(body: PropertyIn, db: Session = Depends(get_db),
                    user: User = Depends(admin)):
    p = AccommodationProperty(tenant_id=user.tenant_id, name=body.name.strip(),
                              city=body.city.strip(), status="locally_recorded",
                              recorded_by=user.id)
    db.add(p)
    db.flush()
    audit(db, user, p, "accommodation_property_recorded")
    db.commit()
    return property_view(p)


@router.get("/properties")
def properties(db: Session = Depends(get_db), user: User = Depends(staff)):
    xs = db.scalars(select(AccommodationProperty).where(
        AccommodationProperty.tenant_id == user.tenant_id,
        AccommodationProperty.status == "locally_recorded").order_by(
            AccommodationProperty.created_at.desc()).limit(100)).all()
    return {"items": [property_view(x) for x in xs], "partner_contracts_verified": False}


class InventoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_type: Literal["single", "double", "accessible"]
    starts_on: date
    ends_on: date
    proposed_rooms: int = Field(ge=1, le=100)
    reference: str = Field(min_length=6, max_length=100, pattern=REF)


@router.post("/properties/{property_id}/inventory", status_code=201)
def propose_inventory(property_id: str, body: InventoryIn,
                      db: Session = Depends(get_db), user: User = Depends(admin)):
    current_window(body.starts_on, body.ends_on)
    p = property_row(db, user, property_id, lock=True)
    if p.status != "locally_recorded":
        raise HTTPException(409, "Inactive accommodation property")
    overlap = db.scalar(select(AccommodationInventory).where(
        AccommodationInventory.tenant_id == user.tenant_id,
        AccommodationInventory.property_id == p.id,
        AccommodationInventory.room_type == body.room_type,
        AccommodationInventory.status == "proposed",
        AccommodationInventory.starts_on < body.ends_on,
        AccommodationInventory.ends_on > body.starts_on).limit(1))
    if overlap:
        raise HTTPException(409, "Overlapping capacity declarations; revoke old declaration first")
    entry = AccommodationInventory(tenant_id=user.tenant_id, property_id=p.id,
       room_type=body.room_type, starts_on=body.starts_on, ends_on=body.ends_on,
       proposed_rooms=body.proposed_rooms, reference=body.reference,
       status="proposed", recorded_by=user.id)
    db.add(entry)
    db.flush()
    audit(db, user, entry, "accommodation_inventory_proposed")
    db.commit()
    return inventory_view(entry)


@router.get("/properties/{property_id}/inventory")
def inventory(property_id: str, db: Session = Depends(get_db),
              user: User = Depends(staff)):
    p = property_row(db, user, property_id)
    rows = db.scalars(select(AccommodationInventory).where(
        AccommodationInventory.tenant_id == user.tenant_id,
        AccommodationInventory.property_id == p.id).order_by(
            AccommodationInventory.starts_on.desc()).limit(100)).all()
    return {"items": [inventory_view(i) for i in rows], "actual_capacity_connected": False}


@router.post("/inventory/{inventory_id}/revoke")
def revoke_inventory(inventory_id: str, db: Session = Depends(get_db),
                     user: User = Depends(admin)):
    # Read ID only to determine the shared lock target.
    candidate = db.scalar(select(AccommodationInventory).where(
        AccommodationInventory.tenant_id == user.tenant_id,
        AccommodationInventory.id == inventory_id))
    if candidate is None:
        raise HTTPException(404, "Inventory not found")
    p = property_row(db, user, candidate.property_id, lock=True)
    entry = db.scalar(select(AccommodationInventory).where(
        AccommodationInventory.id == inventory_id,
        AccommodationInventory.tenant_id == user.tenant_id,
        AccommodationInventory.property_id == p.id).with_for_update())
    if entry.status == "revoked":
        return inventory_view(entry)
    in_use = db.scalar(select(AccommodationStay.id).where(
        AccommodationStay.tenant_id == user.tenant_id,
        AccommodationStay.inventory_id == entry.id,
        AccommodationStay.status.in_(HELD)).limit(1))
    if in_use:
        raise HTTPException(409, "Active internal allocations must be resolved before revocation")
    entry.status = "revoked"
    audit(db, user, entry, "accommodation_inventory_revoked")
    db.commit()
    return inventory_view(entry)


class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=100, pattern=KEY)
    property_id: str
    room_type: Literal["single", "double", "accessible"]
    starts_on: date
    ends_on: date
    rooms_requested: int = Field(ge=1, le=5)
    guests: int = Field(ge=1, le=20)


@router.post("/cases/{case_id}/stays", status_code=201)
def request_stay(case_id: str, body: RequestIn,
                 db: Session = Depends(get_db), user: User = Depends(staff)):
    current_window(body.starts_on, body.ends_on)
    if body.guests > body.rooms_requested * 4:
        raise HTTPException(422, "Guest count exceeds internal room planning limit")
    case, patient = authorized_case(db, user, case_id, lock=True)
    p = property_row(db, user, body.property_id, lock=True)
    if p.status != "locally_recorded":
        raise HTTPException(409, "Inactive property")
    old = db.scalar(select(AccommodationStay).where(
        AccommodationStay.tenant_id == user.tenant_id,
        AccommodationStay.case_id == case.id,
        AccommodationStay.request_key == body.request_key))
    if old is not None:
        if (old.status == "blocked" or
            (old.property_id, old.room_type, old.starts_on, old.ends_on,
             old.rooms_requested, old.guests) !=
            (p.id, body.room_type, body.starts_on, body.ends_on,
             body.rooms_requested, body.guests)):
            raise HTTPException(409, "Idempotency key conflict or previously blocked request")
        return {**stay_view(old), "reused": True}
    row = AccommodationStay(tenant_id=user.tenant_id, case_id=case.id,
        patient_id=patient.id, property_id=p.id, request_key=body.request_key,
        room_type=body.room_type, starts_on=body.starts_on, ends_on=body.ends_on,
        rooms_requested=body.rooms_requested, guests=body.guests,
        status="requested", created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user, row, "accommodation_stay_requested")
    db.add(CaseTimeline(tenant_id=user.tenant_id, case_id=case.id,
                        actor_id=user.id, event="accommodation_stay_requested",
                        details="stay=" + row.id + ";internal_only"))
    db.commit()
    return {**stay_view(row), "reused": False}


@router.get("/cases/{case_id}/stays")
def case_stays(case_id: str, db: Session = Depends(get_db),
               user: User = Depends(staff)):
    case, patient = authorized_case(db, user, case_id)
    rows = db.scalars(select(AccommodationStay).where(
        AccommodationStay.tenant_id == user.tenant_id,
        AccommodationStay.case_id == case.id,
        AccommodationStay.patient_id == patient.id).order_by(
            AccommodationStay.created_at.desc()).limit(100)).all()
    return {"items": [stay_view(row) for row in rows], "hotel_reservation_live": False}


def find_capacity(db: Session, user: User, stay: AccommodationStay):
    stock = db.scalar(select(AccommodationInventory).where(
        AccommodationInventory.tenant_id == user.tenant_id,
        AccommodationInventory.property_id == stay.property_id,
        AccommodationInventory.room_type == stay.room_type,
        AccommodationInventory.status == "proposed",
        AccommodationInventory.starts_on <= stay.starts_on,
        AccommodationInventory.ends_on >= stay.ends_on).limit(1))
    if stock is None:
        raise HTTPException(409, "No covering locally proposed inventory")
    overlapping = db.scalars(select(AccommodationStay).where(
        AccommodationStay.tenant_id == user.tenant_id,
        AccommodationStay.property_id == stay.property_id,
        AccommodationStay.inventory_id == stock.id,
        AccommodationStay.status.in_(HELD),
        AccommodationStay.starts_on < stay.ends_on,
        AccommodationStay.ends_on > stay.starts_on)).all()
    # Exact night-by-night demand, half-open interval avoids departure day errors.
    for day_offset in range((stay.ends_on - stay.starts_on).days):
        night = stay.starts_on + timedelta(days=day_offset)
        occupied = sum(other.rooms_requested for other in overlapping
                       if other.starts_on <= night < other.ends_on)
        if occupied + stay.rooms_requested > stock.proposed_rooms:
            raise HTTPException(409, "Local capacity exceeded on at least one night")
    return stock


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_key: str = Field(min_length=8, max_length=100, pattern=KEY)
    action: Literal["hold_internally", "report_provider_request",
                    "report_provider_confirmation", "report_provider_decline", "cancel"]
    reference: str = Field(min_length=6, max_length=100, pattern=REF)
    supplier_name: str | None = Field(default=None, min_length=6, max_length=100,
                                      pattern=r"^[A-Za-z][A-Za-z0-9 ._/-]{5,99}$")


def digest(body: DecisionIn) -> str:
    return hashlib.sha256(body.model_dump_json().encode()).hexdigest()


@router.post("/stays/{stay_id}/transition")
def transition(stay_id: str, body: DecisionIn,
               db: Session = Depends(get_db), user: User = Depends(admin)):
    case, patient, p, stay = stay_row(db, user, stay_id, lock=True)
    previous = db.scalar(select(AccommodationEvent).where(
        AccommodationEvent.tenant_id == user.tenant_id,
        AccommodationEvent.stay_id == stay.id,
        AccommodationEvent.step_key == body.step_key))
    finger = digest(body)
    if previous:
        if previous.fingerprint != finger:
            raise HTTPException(409, "Idempotency key conflict")
        return {**stay_view(stay), "reused": True}
    expected = {
        "hold_internally": "requested",
        "report_provider_request": "internally_held",
        "report_provider_confirmation": "external_request_reported",
        "report_provider_decline": "external_request_reported",
        "cancel": ("requested", "internally_held"),
    }
    allowed = expected[body.action]
    if stay.status not in (allowed if isinstance(allowed, tuple) else (allowed,)):
        raise HTTPException(409, "Invalid accommodation transition")
    if body.action in ("report_provider_request", "report_provider_confirmation",
                       "report_provider_decline") and not body.supplier_name:
        raise HTTPException(422, "Supplier name required for a manually reported contact")
    if body.action in ("hold_internally", "cancel") and body.supplier_name:
        raise HTTPException(422, "Supplier name not used for this action")
    before = stay.status
    if body.action == "hold_internally":
        stock = find_capacity(db, user, stay)
        stay.inventory_id = stock.id
        stay.status = "internally_held"
        stay.internal_reference = body.reference
    elif body.action == "report_provider_request":
        stay.status = "external_request_reported"
        stay.supplier_name = body.supplier_name
        stay.supplier_reference = body.reference
    elif body.action == "report_provider_confirmation":
        stay.status = "external_confirmation_reported"
        stay.supplier_name = body.supplier_name
        stay.supplier_reference = body.reference
    elif body.action == "report_provider_decline":
        stay.status = "external_decline_reported"
        stay.supplier_name = body.supplier_name
        stay.supplier_reference = body.reference
    else:
        stay.status = "cancelled"
    db.add(AccommodationEvent(tenant_id=user.tenant_id, stay_id=stay.id,
          actor_id=user.id, step_key=body.step_key, fingerprint=finger,
          action=body.action, old_status=before, new_status=stay.status,
          reference=body.reference, occurred_at=datetime.now(timezone.utc)))
    audit(db, user, stay, "accommodation_" + body.action)
    db.add(CaseTimeline(tenant_id=user.tenant_id, case_id=case.id,
        actor_id=user.id, event="accommodation_" + body.action,
        details="stay=" + stay.id + ";no_booking_verification"))
    db.commit()
    return {**stay_view(stay), "reused": False}


@router.get("/stays/{stay_id}/history")
def history(stay_id: str, db: Session = Depends(get_db),
            user: User = Depends(staff)):
    case, patient, p, stay = stay_row(db, user, stay_id)
    events = db.scalars(select(AccommodationEvent).where(
        AccommodationEvent.tenant_id == user.tenant_id,
        AccommodationEvent.stay_id == stay.id).order_by(
            AccommodationEvent.occurred_at, AccommodationEvent.id).limit(100)).all()
    return {"items": [
        {"action": e.action, "previous": e.old_status, "current": e.new_status,
         "reference": e.reference, "actor_id": e.actor_id, "at": e.occurred_at}
        for e in events], "supplier_acknowledgment_verified": False}


@router.get("/due")
def due(limit: int = Query(100, ge=1, le=100),
        db: Session = Depends(get_db), user: User = Depends(staff)):
    # No automated vendor reminders or messages, only staff coordination queue.
    today = datetime.now(timezone.utc).date()
    rows = db.scalars(select(AccommodationStay).join(
        Case, Case.id == AccommodationStay.case_id).where(
        AccommodationStay.tenant_id == user.tenant_id,
        Case.tenant_id == user.tenant_id,
        Case.status.notin_(("closed", "cancelled")),
        AccommodationStay.status.in_(ACTIVE),
        AccommodationStay.starts_on <= today + timedelta(days=14)).order_by(
            AccommodationStay.starts_on, AccommodationStay.id).limit(limit)).all()
    return {"items": [
        {"id": s.id, "case_id": s.case_id, "status": s.status,
         "starts_on": s.starts_on, "ends_on": s.ends_on}
        for s in rows if active_consent(db, user.tenant_id, s.patient_id, "intake")
        and active_consent(db, user.tenant_id, s.patient_id, "accommodation_coordination")
    ], "outbound_messages_sent": False}
