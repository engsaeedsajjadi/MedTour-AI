"""Consent-safe internal appointment holds; never confirms real provider bookings."""
from datetime import datetime,timedelta,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Appointment,Case,Patient,Physician,Audit,User
from .enterprise_models import AppointmentSlot,PhysicianAvailability,PhysicianCredential,CaseTimeline
from .security import roles
from .safety_rules import active_consent
router=APIRouter(prefix="/api/v1/appointment-calendar",tags=["administrative calendar"])
staff=roles("admin","operator")
admin=roles("admin")
REF=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
ACTIVE=("requested","internally_confirmed")

def utc(x):
    return x.astimezone(timezone.utc) if x.tzinfo else x.replace(tzinfo=timezone.utc)
def valid_case(db,user,case_id):
    c=db.scalar(select(Case).where(Case.id==case_id,Case.tenant_id==user.tenant_id))
    if not c:raise HTTPException(404,"Case not found")
    p=db.scalar(select(Patient).where(Patient.id==c.patient_id,Patient.tenant_id==user.tenant_id))
    if not p:raise HTTPException(404,"Patient not found")
    if not active_consent(db,user.tenant_id,p.id,"intake"):raise HTTPException(409,"Active intake consent required")
    if c.status in ("cancelled","closed"):raise HTTPException(409,"Inactive case")
    return c,p
def available(db,user,physician_id,start,end):
    doctor=db.scalar(select(Physician).where(Physician.id==physician_id,Physician.tenant_id==user.tenant_id))
    if not doctor:raise HTTPException(404,"Physician not found")
    ev=db.scalar(select(PhysicianCredential).where(PhysicianCredential.physician_id==doctor.id,PhysicianCredential.tenant_id==user.tenant_id))
    if not ev or ev.status!="locally_attested" or utc(ev.expires_at)<=datetime.now(timezone.utc):
        raise HTTPException(409,"Current locally attested physician evidence required")
    slot=db.scalar(select(PhysicianAvailability).where(
        PhysicianAvailability.tenant_id==user.tenant_id,PhysicianAvailability.physician_id==doctor.id,
        PhysicianAvailability.status=="proposed",PhysicianAvailability.starts_at<=start,
        PhysicianAvailability.ends_at>=end).order_by(PhysicianAvailability.id).limit(1))
    if not slot:raise HTTPException(409,"No matching proposed availability")
    overlapping=db.scalar(select(AppointmentSlot).join(Appointment,Appointment.id==AppointmentSlot.appointment_id).where(
        AppointmentSlot.tenant_id==user.tenant_id,AppointmentSlot.physician_id==doctor.id,
        AppointmentSlot.status.in_(ACTIVE),Appointment.requested_at<end,
        AppointmentSlot.ends_at>start).limit(1))
    if overlapping:raise HTTPException(409,"Overlapping internal appointment allocation")
    return slot

class RequestIn(BaseModel):
    case_id:str
    physician_id:str
    starts_at:datetime
    ends_at:datetime
    request_key:str=Field(min_length=8,max_length=100,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")
    @field_validator("starts_at","ends_at")
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None:raise ValueError("Timezone offset required")
        return v

def view(a,s):
    return {"id":a.id,"case_id":a.case_id,"physician_id":a.physician_id,
            "starts_at":a.requested_at,"ends_at":s.ends_at,
            "status":s.status,"availability_id":s.availability_id,
            "reference":s.review_reference,"external_booking_confirmed":False,
            "internal_proposal_only":True}

@router.post("/requests",status_code=201)
def request(body:RequestIn,db:Session=Depends(get_db),user:User=Depends(staff)):
    start,end=utc(body.starts_at),utc(body.ends_at)
    now=datetime.now(timezone.utc)
    if start<=now or start>now+timedelta(days=365) or end<=start or end-start>timedelta(hours=4):
        raise HTTPException(422,"Invalid appointment window")
    case,patient=valid_case(db,user,body.case_id)
    # Lock the shared physician row, serializing all bookings for this doctor in PostgreSQL.
    doctor=db.scalar(select(Physician).where(
        Physician.id==body.physician_id,Physician.tenant_id==user.tenant_id).with_for_update())
    if not doctor:raise HTTPException(404,"Physician not found")
    old=db.scalar(select(AppointmentSlot).where(
        AppointmentSlot.tenant_id==user.tenant_id,AppointmentSlot.case_id==case.id,
        AppointmentSlot.request_key==body.request_key))
    if old:
        a=db.scalar(select(Appointment).where(Appointment.id==old.appointment_id,Appointment.tenant_id==user.tenant_id))
        if old.physician_id!=body.physician_id or utc(a.requested_at)!=start or utc(old.ends_at)!=end:
            raise HTTPException(409,"Idempotency key conflict")
        return {**view(a,old),"reused":True}
    proposed=available(db,user,doctor.id,start,end)
    a=Appointment(tenant_id=user.tenant_id,case_id=case.id,physician_id=doctor.id,
                  requested_at=start,status="requested")
    db.add(a);db.flush()
    s=AppointmentSlot(tenant_id=user.tenant_id,appointment_id=a.id,case_id=case.id,
        patient_id=patient.id,physician_id=doctor.id,availability_id=proposed.id,
        ends_at=end,status="requested",request_key=body.request_key)
    db.add(s);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="calendar_requested",
        entity_type="Appointment",entity_id=a.id))
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=case.id,actor_id=user.id,
        event="calendar_requested",details="appointment="+a.id+";internal_only"))
    db.commit()
    return {**view(a,s),"reused":False}

@router.get("/cases/{case_id}")
def by_case(case_id:str,db:Session=Depends(get_db),user:User=Depends(staff)):
    case,p=valid_case(db,user,case_id)
    rows=db.execute(select(Appointment,AppointmentSlot).join(
        AppointmentSlot,AppointmentSlot.appointment_id==Appointment.id).where(
        AppointmentSlot.tenant_id==user.tenant_id,AppointmentSlot.case_id==case.id,
        AppointmentSlot.patient_id==p.id).order_by(Appointment.requested_at.desc()).limit(100)).all()
    return {"items":[view(a,s) for a,s in rows],"provider_calendar_live":False}

class ReviewIn(BaseModel):
    action:Literal["internally_confirmed","cancelled"]
    reference:str=Field(min_length=6,max_length=100,pattern=REF)

@router.post("/requests/{appointment_id}/review")
def review(appointment_id:str,body:ReviewIn,db:Session=Depends(get_db),user:User=Depends(admin)):
    s=db.scalar(select(AppointmentSlot).where(
        AppointmentSlot.tenant_id==user.tenant_id,
        AppointmentSlot.appointment_id==appointment_id))
    if not s:raise HTTPException(404,"Managed appointment not found")
    a=db.scalar(select(Appointment).where(Appointment.id==appointment_id,
        Appointment.tenant_id==user.tenant_id))
    db.scalar(select(Physician.id).where(Physician.id==s.physician_id,
        Physician.tenant_id==user.tenant_id).with_for_update())
    s=db.scalar(select(AppointmentSlot).where(
        AppointmentSlot.tenant_id==user.tenant_id,
        AppointmentSlot.appointment_id==appointment_id).with_for_update())
    valid_case(db,user,s.case_id)
    if s.status!="requested":raise HTTPException(409,"Appointment not pending")
    if body.action=="internally_confirmed":
        # Never claim a provider-confirmed booking based on an internal reference.
        available_without_self=db.scalar(select(AppointmentSlot).join(
            Appointment,Appointment.id==AppointmentSlot.appointment_id).where(
            AppointmentSlot.id!=s.id,AppointmentSlot.tenant_id==user.tenant_id,
            AppointmentSlot.physician_id==s.physician_id,
            AppointmentSlot.status.in_(ACTIVE),Appointment.requested_at<utc(s.ends_at),
            AppointmentSlot.ends_at>utc(a.requested_at)).limit(1))
        if available_without_self:raise HTTPException(409,"Resource conflict")
        s.status="internally_confirmed"
    else:s.status="cancelled"
    s.reviewed_by=user.id;s.review_reference=body.reference
    if s.status=="cancelled":a.status="cancelled"
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="calendar_"+s.status,
        entity_type="Appointment",entity_id=a.id))
    db.commit()
    return view(a,s)
