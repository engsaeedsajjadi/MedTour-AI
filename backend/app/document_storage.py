"""Private encrypted development uploads; production requires independently audited object storage + malware scan."""
from __future__ import annotations
import hashlib,os,base64,secrets
from pathlib import Path
from io import BytesIO
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form,Header
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .models import User,Case,Patient,Consent,Document,Audit
from .database import get_db
from .security import roles
from .patient_portal import portal_session
from .secure_media import validate_file,s3_ready,scan_clamav,s3_store
from .medical_document_policy import (
    ACTIVE_STATUSES, cleaned_name, document_path, encrypt_local,
    load_document, private_download_response,
)

router=APIRouter(prefix='/api/v1/secure-documents',tags=['secure documents'])
MAX_BYTES=8*1024*1024
MIMES={'application/pdf':b'%PDF-', 'image/png':b'\x89PNG\r\n\x1a\n', 'image/jpeg':b'\xff\xd8\xff'}

def local_enabled():
    return os.getenv('APP_ENV','development') in ('development','test') and os.getenv('ALLOW_DEV_ENCRYPTED_UPLOADS','false').lower()=='true'

def cipher():
    raw=os.getenv('DOCUMENT_ENCRYPTION_KEY','')
    try:key=base64.urlsafe_b64decode(raw)
    except Exception:key=b''
    if len(key)!=32:raise HTTPException(503,'A 32-byte document encryption key is required')
    return AESGCM(key)

def require_consent(db:Session,p:Patient):
    c=db.scalar(select(Consent).where(Consent.tenant_id==p.tenant_id,Consent.patient_id==p.id,
             Consent.purpose=='medical_documents').order_by(Consent.created_at.desc(),Consent.id.desc()).limit(1))
    if not c or not c.accepted:raise HTTPException(409,'Medical document consent is required')

def location(doc_id:str,tenant_id:str):
    return document_path(tenant_id,doc_id)

def sniff(data:bytes):
    return validate_file(data)[0]

@router.post('/cases/{case_id}',status_code=201)
async def upload(case_id:str,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    if not local_enabled() and not s3_ready():raise HTTPException(503,'Approved medical file storage and scanner are not configured')
    c=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==c.patient_id))
    require_consent(db,p)
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise HTTPException(413,'Document exceeds 8 MiB')
    if not raw:raise HTTPException(422,'Empty document')
    mime, digest=validate_file(raw)
    if s3_ready():scan_clamav(raw)
    # Store checked files only. Dev encryption remains explicitly unscanned.
    name=cleaned_name(file.filename)
    row=Document(tenant_id=user.tenant_id,patient_id=p.id,case_id=c.id,filename=name,
        category='report',status='scanned_private_s3' if s3_ready() else 'encrypted_dev_unscanned',
        mime_type=mime,size_bytes=len(raw),sha256_hex=digest)
    db.add(row);db.flush()
    key=location(row.id,user.tenant_id)
    try:
        if s3_ready():
            row.storage_key=s3_store(user.tenant_id,row.id,raw,mime)
            event='scanned_s3_document_uploaded'
        else:
            encrypt_local(raw,user.tenant_id,row.id,cipher())
            row.storage_key=row.id+'.enc'
            event='dev_encrypted_document_uploaded'
        db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event=event,entity_type='Document',entity_id=row.id))
        db.commit()
    except Exception:
        db.rollback()
        if not s3_ready():key.unlink(missing_ok=True)
        raise
    return {'id':row.id,'status':row.status,'mime_type':mime,'byte_length':len(raw),'production_approved':False}

@router.get('/{document_id}')
def download(document_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    if not local_enabled() and not s3_ready():
        raise HTTPException(503,'Approved medical document storage is disabled')
    row=db.scalar(select(Document).where(
        Document.tenant_id==user.tenant_id, Document.id==document_id,
        Document.status.in_(ACTIVE_STATUSES),
    ))
    if not row:raise HTTPException(404,'Document unavailable')
    patient=db.scalar(select(Patient).where(
        Patient.tenant_id==user.tenant_id,Patient.id==row.patient_id
    ))
    case=db.scalar(select(Case).where(
        Case.tenant_id==user.tenant_id,Case.id==row.case_id,Case.patient_id==row.patient_id
    ))
    if not patient or not case:raise HTTPException(404,'Document not in patient case')
    require_consent(db,patient)
    raw,mime=load_document(row,user.tenant_id,local_enabled=local_enabled(),cipher_factory=cipher)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event='medical_document_accessed',entity_type='Document',entity_id=row.id))
    db.commit()
    return private_download_response(raw,mime)


@router.get('/readiness')
def document_readiness(user:User=Depends(roles('admin','operator'))):
    return {
        'storage_mode': 'local_encrypted_unscanned_test' if local_enabled() else
            's3_kms_configured_unverified' if s3_ready() else 'disabled',
        'configured':bool(local_enabled() or s3_ready()),
        'actual_s3_kms_scanner_verified':False,
        'production_ready':False,
        'real_patient_documents_allowed':False,
        'patient_portal_identity_assurance_complete':False,
    }


@router.get('/cases/{case_id}/list')
def list_docs(case_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    c=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==c.patient_id))
    if not p:raise HTTPException(404,'Patient not found')
    require_consent(db,p)
    rows=db.scalars(select(Document).where(
        Document.tenant_id==user.tenant_id,Document.case_id==case_id,
        Document.patient_id==p.id,Document.status.in_(ACTIVE_STATUSES)
    ).order_by(Document.created_at.desc()).limit(100)).all()
    return [{'id':x.id,'filename':x.filename,'status':x.status,'category':x.category,'created_at':x.created_at} for x in rows]


@router.post('/portal/cases/{case_id}',status_code=201)
async def patient_upload(case_id:str,file:UploadFile=File(...),
    x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    """Patient uploads directly from the secure portal, never from WhatsApp chat."""
    if not local_enabled() and not s3_ready():
        raise HTTPException(503,'Approved medical file storage and scanner are not configured')
    grant=portal_session(x_patient_access,db)
    c=db.scalar(select(Case).where(Case.tenant_id==grant.tenant_id,Case.patient_id==grant.patient_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    p=db.scalar(select(Patient).where(Patient.tenant_id==grant.tenant_id,Patient.id==grant.patient_id))
    require_consent(db,p)
    raw=await file.read(MAX_BYTES+1)
    mime,digest=validate_file(raw)
    if s3_ready():scan_clamav(raw)
    name=cleaned_name(file.filename)
    row=Document(tenant_id=grant.tenant_id,patient_id=p.id,case_id=c.id,filename=name,
        category='report',status='scanned_private_s3' if s3_ready() else 'encrypted_dev_unscanned',
        mime_type=mime,size_bytes=len(raw),sha256_hex=digest)
    db.add(row);db.flush()
    location_key=location(row.id,grant.tenant_id)
    try:
        if s3_ready():
            row.storage_key=s3_store(grant.tenant_id,row.id,raw,mime)
        else:
            encrypt_local(raw,grant.tenant_id,row.id,cipher())
            row.storage_key=row.id+'.enc'
        db.add(Audit(tenant_id=grant.tenant_id,user_id=p.id,event='portal_document_uploaded',entity_type='Document',entity_id=row.id))
        db.commit()
    except Exception:
        db.rollback()
        if not s3_ready():location_key.unlink(missing_ok=True)
        raise
    return {'id':row.id,'status':row.status,'mime_type':mime,'byte_length':len(raw),'production_approved':False}

@router.get('/portal/cases/{case_id}/list')
def patient_list_docs(case_id:str,x_patient_access:str|None=Header(None,alias='X-Patient-Access'),db:Session=Depends(get_db)):
    grant=portal_session(x_patient_access,db)
    c=db.scalar(select(Case).where(Case.tenant_id==grant.tenant_id,Case.patient_id==grant.patient_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    p=db.scalar(select(Patient).where(Patient.tenant_id==grant.tenant_id,Patient.id==grant.patient_id))
    require_consent(db,p)
    rows=db.scalars(select(Document).where(
        Document.tenant_id==grant.tenant_id,Document.case_id==case_id,
        Document.patient_id==p.id,Document.status.in_(ACTIVE_STATUSES)
    ).order_by(Document.created_at.desc()).limit(100)).all()
    return [{'id':d.id,'filename':d.filename,'status':d.status,'created_at':d.created_at} for d in rows]

@router.get('/portal/cases/{case_id}/documents/{document_id}')
def patient_download(case_id:str,document_id:str,
    x_patient_access:str|None=Header(None,alias='X-Patient-Access'),
    db:Session=Depends(get_db)):
    if not local_enabled() and not s3_ready():
        raise HTTPException(503,'Approved medical document storage is disabled')
    grant=portal_session(x_patient_access,db)
    case=db.scalar(select(Case).where(
        Case.id==case_id,Case.tenant_id==grant.tenant_id,
        Case.patient_id==grant.patient_id))
    if not case:raise HTTPException(404,'Case not found')
    patient=db.scalar(select(Patient).where(
        Patient.id==grant.patient_id,Patient.tenant_id==grant.tenant_id))
    if not patient:raise HTTPException(404,'Patient not found')
    require_consent(db,patient)
    row=db.scalar(select(Document).where(
        Document.id==document_id, Document.tenant_id==grant.tenant_id,
        Document.patient_id==patient.id, Document.case_id==case.id,
        Document.status.in_(ACTIVE_STATUSES),
    ))
    if not row:raise HTTPException(404,'Document not available')
    raw,mime=load_document(row,grant.tenant_id,
        local_enabled=local_enabled(),cipher_factory=cipher)
    db.add(Audit(tenant_id=grant.tenant_id,user_id=grant.issued_by,
        event='portal_medical_document_accessed',entity_type='Document',entity_id=row.id))
    db.commit()
    return private_download_response(raw,mime)
