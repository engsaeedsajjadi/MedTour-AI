"""Section 14 administrative provider matching: no medical recommendations."""
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Case,Patient,Physician,Hospital,Audit
from .enterprise_models import ProviderMatch,PhysicianCredential,PhysicianAffiliation,HospitalCredential,HospitalService,CaseTimeline
from .security import roles
from .safety_rules import active_consent

router=APIRouter(prefix="/api/v1/provider-matching",tags=["nonclinical provider matching"])
staff=roles("admin","operator")
admin=roles("admin")
REF=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"

def current(row):
    expiry=row.expires_at
    if expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
    return row.status=="locally_attested" and expiry>datetime.now(timezone.utc)

def case_patient(db,user,id):
    case=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==id))
    if not case:raise HTTPException(404,"Case not found")
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==case.patient_id))
    if not p:raise HTTPException(404,"Patient not found")
    if not active_consent(db,user.tenant_id,p.id,"intake"):
        raise HTTPException(409,"Active intake consent required")
    return case,p

def eligible(db,user,case,physician_id,hospital_id):
    doctor=db.scalar(select(Physician).where(Physician.tenant_id==user.tenant_id,Physician.id==physician_id))
    if not doctor:raise HTTPException(404,"Physician not found")
    evidence=db.scalar(select(PhysicianCredential).where(
        PhysicianCredential.tenant_id==user.tenant_id,PhysicianCredential.physician_id==doctor.id))
    if not evidence or not current(evidence):raise HTTPException(409,"Current local physician credential evidence required")
    if doctor.specialty.strip().casefold()!=case.specialty.strip().casefold():
        raise HTTPException(409,"Directory specialty does not match case specialty text")
    hospital=None
    if hospital_id:
        hospital=db.scalar(select(Hospital).where(Hospital.tenant_id==user.tenant_id,Hospital.id==hospital_id))
        if not hospital:raise HTTPException(404,"Hospital not found")
        credential=db.scalar(select(HospitalCredential).where(
            HospitalCredential.tenant_id==user.tenant_id,HospitalCredential.hospital_id==hospital.id))
        if not credential or not current(credential):
            raise HTTPException(409,"Current local hospital evidence required")
        affiliation=db.scalar(select(PhysicianAffiliation).where(
            PhysicianAffiliation.tenant_id==user.tenant_id,PhysicianAffiliation.physician_id==doctor.id,
            PhysicianAffiliation.hospital_id==hospital.id,PhysicianAffiliation.status=="locally_recorded"))
        service=db.scalar(select(HospitalService).where(
            HospitalService.tenant_id==user.tenant_id,HospitalService.hospital_id==hospital.id,
            HospitalService.service_code==case.specialty.strip().casefold(),HospitalService.status=="locally_recorded"))
        if not affiliation or not service:raise HTTPException(409,"Hospital service or affiliation not locally recorded")
    return doctor,hospital

def view(x):
    return {"id":x.id,"case_id":x.case_id,"physician_id":x.physician_id,
            "hospital_id":x.hospital_id,"status":x.status,
            "review_reference":x.review_reference,
            "clinical_suitability_determined":False,
            "external_credentials_verified":False,"booking_created":False}

@router.get("/cases/{case_id}/options")
def options(case_id:str,db:Session=Depends(get_db),user:User=Depends(staff)):
    case,p=case_patient(db,user,case_id)
    doctors=db.scalars(select(Physician).where(Physician.tenant_id==user.tenant_id).order_by(Physician.id).limit(200)).all()
    items=[]
    for doctor in doctors:
        if doctor.specialty.strip().casefold()!=case.specialty.strip().casefold():continue
        row=db.scalar(select(PhysicianCredential).where(PhysicianCredential.tenant_id==user.tenant_id,PhysicianCredential.physician_id==doctor.id))
        if row and current(row):
            items.append({"physician_id":doctor.id,"name":doctor.full_name,
             "specialty":doctor.specialty,"city":doctor.city,
             "reason":"Exact directory specialty text and locally attested unexpired credential",
             "hospital_affiliation_verified":False,"regulator_licence_verified":False})
    return {"items":items[:50],"results_bounded":True,"clinical_ranking":False,
            "independent_regulator_verification":False,"requires_qualified_human":True}

class ProposeIn(BaseModel):
    physician_id:str
    hospital_id:str|None=None

@router.post("/cases/{case_id}/proposals",status_code=201)
def propose(case_id:str,body:ProposeIn,db:Session=Depends(get_db),user:User=Depends(staff)):
    case,p=case_patient(db,user,case_id)
    if case.status in ("closed","cancelled"):raise HTTPException(409,"Case inactive")
    eligible(db,user,case,body.physician_id,body.hospital_id)
    db.scalar(select(Case.id).where(Case.id==case.id,Case.tenant_id==user.tenant_id).with_for_update())
    old=db.scalar(select(ProviderMatch).where(
        ProviderMatch.tenant_id==user.tenant_id,ProviderMatch.case_id==case.id,
        ProviderMatch.physician_id==body.physician_id,
        ProviderMatch.hospital_id==body.hospital_id))
    if old:return {**view(old),"reused":True}
    row=ProviderMatch(tenant_id=user.tenant_id,case_id=case.id,patient_id=p.id,
                      physician_id=body.physician_id,hospital_id=body.hospital_id,
                      status="pending_human_review",proposed_by=user.id)
    db.add(row);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="provider_match_proposed",entity_type="ProviderMatch",entity_id=row.id))
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=case.id,actor_id=user.id,
                        event="provider_match_proposed",details="match="+row.id+";administrative_only"))
    db.commit()
    return {**view(row),"reused":False}

@router.get("/cases/{case_id}/proposals")
def proposals(case_id:str,db:Session=Depends(get_db),user:User=Depends(staff)):
    case,p=case_patient(db,user,case_id)
    items=db.scalars(select(ProviderMatch).where(
        ProviderMatch.tenant_id==user.tenant_id,ProviderMatch.case_id==case.id,
        ProviderMatch.patient_id==p.id).order_by(ProviderMatch.created_at.desc()).limit(100)).all()
    return {"items":[view(x) for x in items],"clinical_decision":False}

class DecisionIn(BaseModel):
    decision:Literal["administratively_shortlisted","rejected"]
    reference:str=Field(min_length=6,max_length=100,pattern=REF)

@router.post("/proposals/{match_id}/review")
def review(match_id:str,body:DecisionIn,db:Session=Depends(get_db),user:User=Depends(admin)):
    row=db.scalar(select(ProviderMatch).where(
        ProviderMatch.tenant_id==user.tenant_id,ProviderMatch.id==match_id).with_for_update())
    if not row:raise HTTPException(404,"Proposal not found")
    case,p=case_patient(db,user,row.case_id)
    if row.patient_id!=p.id:raise HTTPException(409,"Mismatched patient")
    if row.status!="pending_human_review":raise HTTPException(409,"Already reviewed")
    if body.decision=="administratively_shortlisted":
        eligible(db,user,case,row.physician_id,row.hospital_id)
    row.status=body.decision;row.review_reference=body.reference
    row.reviewed_by=user.id;row.reviewed_at=datetime.now(timezone.utc)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="provider_match_"+row.status,
                 entity_type="ProviderMatch",entity_id=row.id))
    db.commit()
    return view(row)
