"""Patient-driven, structured, consent-gated non-diagnostic intake."""
from __future__ import annotations
import json
from fastapi import APIRouter,Header,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .patient_portal import portal_session
from .database import get_db
from .models import Case,Patient,Consent
from .enterprise_models import PatientIntake
from .intake import LANGUAGES,QUESTION_KEYS,next_question,intake_response

router=APIRouter(prefix='/api/v1/portal/intake',tags=['patient intake'])

def patient_session(x_patient_access,db):
    grant=portal_session(x_patient_access,db)
    patient=db.scalar(select(Patient).where(Patient.tenant_id==grant.tenant_id,Patient.id==grant.patient_id))
    if not patient:raise HTTPException(404,'Patient missing')
    consent=db.scalar(select(Consent).where(Consent.tenant_id==grant.tenant_id,
      Consent.patient_id==patient.id,Consent.purpose=='intake').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    if not consent or not consent.accepted:raise HTTPException(409,'Intake consent is required')
    return grant,patient

def public_state(row):
    return {'id':row.id,'case_id':row.case_id,'stage':row.stage,'status':row.status,
       'language':row.language,'next_key':QUESTION_KEYS[row.stage] if row.status=='in_progress' and row.stage<len(QUESTION_KEYS) else None,
       'next_prompt':next_question(row.language,row.stage) if row.status=='in_progress' else None,
       'human_review_required':True}

class Start(BaseModel):
    case_id:str
    language:str|None=None

@router.post('/sessions',status_code=201)
def start(body:Start,x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant,p=patient_session(x_patient_access,db)
    c=db.scalar(select(Case).where(Case.tenant_id==grant.tenant_id,Case.id==body.case_id,Case.patient_id==p.id))
    if not c:raise HTTPException(404,'Case not found')
    lang=body.language or p.language
    if lang not in LANGUAGES:raise HTTPException(422,'Unsupported language')
    last=db.scalar(select(PatientIntake).where(PatientIntake.tenant_id==grant.tenant_id,
        PatientIntake.case_id==c.id).order_by(PatientIntake.created_at.desc(),PatientIntake.id.desc()).limit(1))
    if last and last.status=='in_progress':return public_state(last)
    if last and last.status=='requires_urgent_human_review':raise HTTPException(409,'Awaiting urgent human review')
    if last and last.status=='awaiting_clinician_review':raise HTTPException(409,'Already submitted for review')
    row=PatientIntake(tenant_id=grant.tenant_id,case_id=c.id,language=lang)
    db.add(row);db.commit();db.refresh(row)
    return public_state(row)

class Answer(BaseModel):
    answer:str=Field(min_length=1,max_length=3000)

@router.post('/sessions/{session_id}/answer')
def answer(session_id:str,body:Answer,x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant,p=patient_session(x_patient_access,db)
    row=db.scalar(select(PatientIntake).join(Case,PatientIntake.case_id==Case.id).where(
        PatientIntake.tenant_id==grant.tenant_id,PatientIntake.id==session_id,Case.tenant_id==grant.tenant_id,Case.patient_id==p.id))
    if not row:raise HTTPException(404,'Intake session not found')
    if row.status!='in_progress':raise HTTPException(409,'Intake session already completed')
    safety=intake_response(row.language,body.answer)
    if safety['emergency_keyword_detected']:
        row.status='requires_urgent_human_review';db.commit()
        return {**public_state(row),'emergency_keyword_detected':True,'warning':safety['message']}
    if row.stage>=len(QUESTION_KEYS):raise HTTPException(409,'Intake complete')
    data=json.loads(row.answers_json)
    data[QUESTION_KEYS[row.stage]]=body.answer
    row.answers_json=json.dumps(data,ensure_ascii=False)
    row.stage+=1
    if row.stage==len(QUESTION_KEYS):row.status='awaiting_clinician_review'
    db.commit()
    return {**public_state(row),'emergency_keyword_detected':False}

@router.get('/sessions/{session_id}')
def read(session_id:str,x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant,p=patient_session(x_patient_access,db)
    row=db.scalar(select(PatientIntake).join(Case,PatientIntake.case_id==Case.id).where(
        PatientIntake.tenant_id==grant.tenant_id,PatientIntake.id==session_id,Case.tenant_id==grant.tenant_id,Case.patient_id==p.id))
    if not row:raise HTTPException(404,'Intake session not found')
    return public_state(row)
