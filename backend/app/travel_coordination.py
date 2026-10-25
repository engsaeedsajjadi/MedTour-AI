"""Section 19: manual, tenant and consent scoped transport/interpreter coordination.

Local proposed availability, staff-entered supplier responses: never a real
booking, dispatch, professional credential check or medical interpretation.
Do not store identifiers, passenger addresses, flight numbers or medical text.
"""
from datetime import datetime,timedelta,timezone
import hashlib
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Audit,Case,Patient,User
from .enterprise_models import TravelResource,TravelResourceWindow,TravelAssignment,TravelAssignmentEvent,CaseTimeline
from .security import roles
from .safety_rules import active_consent

router=APIRouter(prefix="/api/v1/travel-coordination",tags=["manual travel coordination"])
STAFF=roles("admin","operator")
ADMIN=roles("admin")
REF=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
KEY=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$"
KIND={"airport_pickup":"vehicle","airport_dropoff":"vehicle","city_transfer":"vehicle",
      "interpreter_session":"interpreter"}
CONSENT={"vehicle":"transport_coordination","interpreter":"interpreter_coordination"}
LANGUAGES=("fa","en","ar","ps","prs")
RESERVED=("internally_allocated","provider_contact_reported","provider_ack_reported","blocked")


def utc(value:datetime)->datetime:
    return value.astimezone(timezone.utc)


def validate_time(start,end):
    now=datetime.now(timezone.utc)
    start,end=utc(start),utc(end)
    if not (now<start<now+timedelta(days=365) and start<end<=start+timedelta(hours=8)):
        raise HTTPException(422,"Future time window must be at most 8 hours")
    return start,end


def log(db,user,row,event):
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        entity_type=type(row).__name__,entity_id=row.id,event=event))


def require_case(db,user,id,kind,lock=False):
    stmt=select(Case).where(Case.id==id,Case.tenant_id==user.tenant_id)
    c=db.scalar(stmt.with_for_update() if lock else stmt)
    if not c:raise HTTPException(404,"Case not found")
    p=db.scalar(select(Patient).where(Patient.id==c.patient_id,Patient.tenant_id==user.tenant_id))
    if not p:raise HTTPException(404,"Patient not found")
    if not active_consent(db,user.tenant_id,p.id,"intake") or not active_consent(
        db,user.tenant_id,p.id,CONSENT[KIND[kind]]):
        raise HTTPException(409,"Active intake and specific coordination consent required")
    if c.status in ("closed","cancelled"):raise HTTPException(409,"Inactive case")
    return c,p


def require_resource(db,user,id,lock=False):
    stmt=select(TravelResource).where(TravelResource.id==id,TravelResource.tenant_id==user.tenant_id)
    r=db.scalar(stmt.with_for_update() if lock else stmt)
    if not r:raise HTTPException(404,"Resource not found")
    if r.status!="locally_attested":raise HTTPException(409,"Resource inactive")
    return r


def require_request(db,user,id,lock=False):
    original=db.scalar(select(TravelAssignment).where(
        TravelAssignment.id==id,TravelAssignment.tenant_id==user.tenant_id))
    if not original:raise HTTPException(404,"Request not found")
    c,p=require_case(db,user,original.case_id,original.kind,lock)
    r=require_resource(db,user,original.resource_id,lock)
    stmt=select(TravelAssignment).where(
        TravelAssignment.id==id,TravelAssignment.tenant_id==user.tenant_id,
        TravelAssignment.case_id==c.id,TravelAssignment.patient_id==p.id,
        TravelAssignment.resource_id==r.id)
    item=db.scalar(stmt.with_for_update() if lock else stmt)
    if not item:raise HTTPException(404,"Request not found")
    if item.status=="blocked":raise HTTPException(409,"Request permanently blocked after consent withdrawal")
    return c,p,r,item


def resource_view(x):
    return dict(id=x.id,kind=x.kind,label=x.label,city=x.city,seats=x.seats,language=x.language,
        status=x.status,independent_licence_verified=False,provider_connected=False)


def availability_view(x):
    return dict(id=x.id,resource_id=x.resource_id,starts_at=x.starts_at,ends_at=x.ends_at,
        status=x.status,reference=x.reference,live_availability=False)


def request_view(x):
    return dict(id=x.id,case_id=x.case_id,resource_id=x.resource_id,kind=x.kind,
        starts_at=x.starts_at,ends_at=x.ends_at,passengers=x.passengers,
        language=x.language,origin_zone=x.origin_zone,destination_zone=x.destination_zone,
        status=x.status,window_id=x.window_id,reference=x.reference,
        supplier_name=x.supplier_name,supplier_reference=x.supplier_reference,external_dispatch_verified=False,
        interpreter_credential_verified=False,internal_coordination_only=True)


class ResourceIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind:Literal["vehicle","interpreter"]
    label:str=Field(min_length=3,max_length=120,pattern=r"^[^\x00-\x1F\x7F]+$")
    city:str=Field(min_length=2,max_length=80,pattern=r"^[^\x00-\x1F\x7F]+$")
    seats:int=Field(ge=1,le=8)
    language:Literal["fa","en","ar","ps","prs"]|None=None


@router.post("/resources",status_code=201)
def resource_create(body:ResourceIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if (body.kind=="vehicle" and body.language is not None) or (
        body.kind=="interpreter" and (body.language is None or body.seats!=1)):
        raise HTTPException(422,"Invalid resource language or capacity")
    row=TravelResource(tenant_id=user.tenant_id,**body.model_dump(),
        status="locally_attested",recorded_by=user.id)
    db.add(row);db.flush();log(db,user,row,"travel_resource_recorded");db.commit()
    return resource_view(row)


@router.get("/resources")
def resources(kind:Literal["vehicle","interpreter"]|None=None,
        db:Session=Depends(get_db),user:User=Depends(STAFF)):
    stmt=select(TravelResource).where(TravelResource.tenant_id==user.tenant_id,
                                     TravelResource.status=="locally_attested")
    if kind:stmt=stmt.where(TravelResource.kind==kind)
    xs=db.scalars(stmt.order_by(TravelResource.created_at.desc()).limit(100)).all()
    return {"items":[resource_view(x) for x in xs],"provider_qualifications_verified":False}


class WindowIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    starts_at:datetime
    ends_at:datetime
    reference:str=Field(min_length=6,max_length=100,pattern=REF)

    @field_validator("starts_at","ends_at")
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError("Timezone required")
        return value


@router.post("/resources/{resource_id}/windows",status_code=201)
def window_create(resource_id:str,body:WindowIn,
        db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    start,end=validate_time(body.starts_at,body.ends_at)
    r=require_resource(db,user,resource_id,lock=True)
    clash=db.scalar(select(TravelResourceWindow).where(
        TravelResourceWindow.tenant_id==user.tenant_id,
        TravelResourceWindow.resource_id==r.id,TravelResourceWindow.status=="proposed",
        TravelResourceWindow.starts_at<end,TravelResourceWindow.ends_at>start).limit(1))
    if clash:raise HTTPException(409,"Overlapping local availability")
    w=TravelResourceWindow(tenant_id=user.tenant_id,resource_id=r.id,
        starts_at=start,ends_at=end,status="proposed",reference=body.reference,recorded_by=user.id)
    db.add(w);db.flush();log(db,user,w,"travel_availability_proposed");db.commit()
    return availability_view(w)


@router.get("/resources/{resource_id}/windows")
def windows(resource_id:str,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    r=require_resource(db,user,resource_id)
    xs=db.scalars(select(TravelResourceWindow).where(
        TravelResourceWindow.tenant_id==user.tenant_id,
        TravelResourceWindow.resource_id==r.id).order_by(
            TravelResourceWindow.starts_at.desc()).limit(100)).all()
    return {"items":[availability_view(x) for x in xs],"live_inventory":False}


@router.post("/windows/{window_id}/revoke")
def revoke(window_id:str,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    candidate=db.scalar(select(TravelResourceWindow).where(
        TravelResourceWindow.tenant_id==user.tenant_id,TravelResourceWindow.id==window_id))
    if not candidate:raise HTTPException(404,"Window not found")
    r=require_resource(db,user,candidate.resource_id,lock=True)
    w=db.scalar(select(TravelResourceWindow).where(
        TravelResourceWindow.id==window_id,TravelResourceWindow.resource_id==r.id,
        TravelResourceWindow.tenant_id==user.tenant_id).with_for_update())
    if w.status=="revoked":return availability_view(w)
    active=db.scalar(select(TravelAssignment.id).where(
        TravelAssignment.tenant_id==user.tenant_id,TravelAssignment.window_id==w.id,
        TravelAssignment.status.in_(RESERVED)).limit(1))
    if active:raise HTTPException(409,"Resource already allocated; manual reconciliation needed")
    w.status="revoked";log(db,user,w,"travel_availability_revoked");db.commit()
    return availability_view(w)


class RequestIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=8,max_length=100,pattern=KEY)
    resource_id:str
    kind:Literal["airport_pickup","airport_dropoff","city_transfer","interpreter_session"]
    starts_at:datetime
    ends_at:datetime
    passengers:int=Field(ge=1,le=8)
    language:Literal["fa","en","ar","ps","prs"]|None=None
    origin_zone:Literal["airport","hotel","hospital","city_center","not_applicable"]
    destination_zone:Literal["airport","hotel","hospital","city_center","not_applicable"]

    @field_validator("starts_at","ends_at")
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError("Timezone required")
        return value


@router.post("/cases/{case_id}/requests",status_code=201)
def request_create(case_id:str,body:RequestIn,db:Session=Depends(get_db),
        user:User=Depends(STAFF)):
    start,end=validate_time(body.starts_at,body.ends_at)
    c,p=require_case(db,user,case_id,body.kind,lock=True)
    r=require_resource(db,user,body.resource_id,lock=True)
    if KIND[body.kind]!=r.kind:raise HTTPException(422,"Resource type mismatch")
    if body.kind=="airport_pickup" and body.origin_zone!="airport":
        raise HTTPException(422,"Airport pickup must begin at airport")
    if body.kind=="airport_dropoff" and body.destination_zone!="airport":
        raise HTTPException(422,"Airport dropoff must end at airport")
    if r.kind=="interpreter":
        if body.language!=r.language or body.passengers!=1 or body.origin_zone!="not_applicable" or body.destination_zone!="not_applicable":
            raise HTTPException(422,"Interpreter language or metadata invalid")
    elif (body.language is not None or body.passengers>r.seats or
          "not_applicable" in (body.origin_zone,body.destination_zone) or
          body.origin_zone==body.destination_zone):
        raise HTTPException(422,"Vehicle capacity or zones invalid")
    existing=db.scalar(select(TravelAssignment).where(
        TravelAssignment.tenant_id==user.tenant_id,
        TravelAssignment.case_id==c.id,TravelAssignment.request_key==body.request_key))
    if existing:
        prior=(existing.resource_id,existing.kind,utc(existing.starts_at),
               utc(existing.ends_at),existing.passengers,existing.language,
               existing.origin_zone,existing.destination_zone)
        current=(r.id,body.kind,start,end,body.passengers,body.language,
                 body.origin_zone,body.destination_zone)
        if existing.status=="blocked" or prior!=current:
            raise HTTPException(409,"Idempotency key conflict")
        return {**request_view(existing),"reused":True}
    x=TravelAssignment(tenant_id=user.tenant_id,case_id=c.id,patient_id=p.id,
        resource_id=r.id,request_key=body.request_key,kind=body.kind,
        starts_at=start,ends_at=end,passengers=body.passengers,language=body.language,
        origin_zone=body.origin_zone,destination_zone=body.destination_zone,
        status="requested",created_by=user.id)
    db.add(x);db.flush();log(db,user,x,"travel_coordination_requested")
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=c.id,actor_id=user.id,
        event="travel_coordination_requested",details="request="+x.id+";manual_only"))
    db.commit()
    return {**request_view(x),"reused":False}


@router.get("/cases/{case_id}/requests")
def requests(case_id:str,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    c=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==case_id))
    if not c:raise HTTPException(404,"Case not found")
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==c.patient_id))
    if not p:raise HTTPException(404,"Patient not found")
    if not active_consent(db,user.tenant_id,p.id,"intake"):
        raise HTTPException(409,"Intake consent required")
    xs=db.scalars(select(TravelAssignment).where(
        TravelAssignment.tenant_id==user.tenant_id,
        TravelAssignment.case_id==c.id,TravelAssignment.patient_id==p.id).order_by(
            TravelAssignment.created_at.desc()).limit(100)).all()
    return {"items":[request_view(x) for x in xs if active_consent(
        db,user.tenant_id,p.id,CONSENT[KIND[x.kind]])],"live_dispatch":False}


class StepIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    step_key:str=Field(min_length=8,max_length=100,pattern=KEY)
    action:Literal["allocate_internally","report_provider_contact","report_provider_ack",
                   "report_provider_decline","cancel"]
    reference:str=Field(min_length=6,max_length=100,pattern=REF)
    supplier_name:str|None=Field(default=None,min_length=6,max_length=100,
                                 pattern=r"^[A-Za-z][A-Za-z0-9 ._/-]{5,99}$")


@router.post("/requests/{request_id}/transition")
def transition(request_id:str,body:StepIn,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    c,p,r,x=require_request(db,user,request_id,lock=True)
    previous=db.scalar(select(TravelAssignmentEvent).where(
        TravelAssignmentEvent.tenant_id==user.tenant_id,
        TravelAssignmentEvent.request_id==x.id,TravelAssignmentEvent.step_key==body.step_key))
    fingerprint=hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    if previous:
        if previous.fingerprint!=fingerprint:raise HTTPException(409,"Idempotency key reused with different payload")
        return {**request_view(x),"reused":True}
    moves={"allocate_internally":("requested",),
           "report_provider_contact":("internally_allocated",),
           "report_provider_ack":("provider_contact_reported",),
           "report_provider_decline":("provider_contact_reported",),
           "cancel":("requested","internally_allocated")}
    if x.status not in moves[body.action]:
        raise HTTPException(409,"Invalid transition")
    if body.action.startswith("report_provider") and not body.supplier_name:
        raise HTTPException(422,"Supplier desk name required")
    if not body.action.startswith("report_provider") and body.supplier_name:
        raise HTTPException(422,"Unexpected supplier name")
    before=x.status
    if body.action=="allocate_internally":
        w=db.scalar(select(TravelResourceWindow).where(
            TravelResourceWindow.tenant_id==user.tenant_id,
            TravelResourceWindow.resource_id==r.id,TravelResourceWindow.status=="proposed",
            TravelResourceWindow.starts_at<=x.starts_at,
            TravelResourceWindow.ends_at>=x.ends_at).limit(1))
        if not w:raise HTTPException(409,"No covering locally proposed availability")
        overlap=db.scalar(select(TravelAssignment.id).where(
            TravelAssignment.tenant_id==user.tenant_id,TravelAssignment.id!=x.id,
            TravelAssignment.resource_id==r.id,
            TravelAssignment.status.in_(RESERVED),TravelAssignment.window_id.is_not(None),
            TravelAssignment.starts_at<x.ends_at,
            TravelAssignment.ends_at>x.starts_at).limit(1))
        if overlap:raise HTTPException(409,"Resource already internally allocated")
        x.status="internally_allocated";x.window_id=w.id;x.reference=body.reference
    elif body.action=="report_provider_contact":
        x.status="provider_contact_reported";x.supplier_name=body.supplier_name;x.supplier_reference=body.reference
    elif body.action=="report_provider_ack":
        x.status="provider_ack_reported";x.supplier_name=body.supplier_name;x.supplier_reference=body.reference
    elif body.action=="report_provider_decline":
        x.status="provider_decline_reported";x.supplier_name=body.supplier_name;x.supplier_reference=body.reference
    else:x.status="cancelled"
    db.add(TravelAssignmentEvent(tenant_id=user.tenant_id,request_id=x.id,
        actor_id=user.id,step_key=body.step_key,fingerprint=fingerprint,
        action=body.action,old_status=before,new_status=x.status,reference=body.reference,
        occurred_at=datetime.now(timezone.utc)))
    log(db,user,x,"travel_coordination_"+body.action)
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=c.id,actor_id=user.id,
        event="travel_coordination_"+body.action,
        details="request="+x.id+";no_external_confirmation"))
    db.commit()
    return {**request_view(x),"reused":False}


@router.get("/requests/{request_id}/history")
def history(request_id:str,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    c,p,r,x=require_request(db,user,request_id)
    xs=db.scalars(select(TravelAssignmentEvent).where(
        TravelAssignmentEvent.tenant_id==user.tenant_id,
        TravelAssignmentEvent.request_id==x.id).order_by(
            TravelAssignmentEvent.occurred_at,TravelAssignmentEvent.id).limit(100)).all()
    return {"items":[dict(action=e.action,before=e.old_status,after=e.new_status,
        reference=e.reference,actor_id=e.actor_id,at=e.occurred_at) for e in xs],
        "provider_confirmation_verified":False}


@router.get("/due")
def due(limit:int=Query(100,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(STAFF)):
    now=datetime.now(timezone.utc)
    rows=db.scalars(select(TravelAssignment).join(Case,Case.id==TravelAssignment.case_id).where(
        TravelAssignment.tenant_id==user.tenant_id,Case.tenant_id==user.tenant_id,
        Case.status.notin_(("cancelled","closed")),
        TravelAssignment.status.in_(("requested","internally_allocated","provider_contact_reported")),
        TravelAssignment.starts_at<=now+timedelta(days=7)).order_by(
            TravelAssignment.starts_at,TravelAssignment.id).limit(limit)).all()
    return {"items":[dict(id=x.id,case_id=x.case_id,kind=x.kind,status=x.status,
                          starts_at=x.starts_at) for x in rows if
        active_consent(db,user.tenant_id,x.patient_id,"intake") and
        active_consent(db,user.tenant_id,x.patient_id,CONSENT[KIND[x.kind]])],
        "automatic_notifications":False}
