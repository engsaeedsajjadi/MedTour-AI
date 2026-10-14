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
from .secure_media import validate_file,s3_ready,scan_clamav,s3_store,s3_load

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
    root=Path(os.getenv('PRIVATE_DOCUMENT_DIR','./.private_documents')).resolve()
    return root/tenant_id/(doc_id+'.enc')

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
    name=Path(file.filename or 'file').name.replace('\x00','')[:180]
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
            nonce=secrets.token_bytes(12)
            encrypted=nonce+cipher().encrypt(nonce,raw,(user.tenant_id+':'+row.id).encode())
            key.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with key.open('xb') as stream:stream.write(encrypted)
            os.chmod(key,0o600)
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
    if not local_enabled() and not s3_ready():raise HTTPException(503,'Approved medical document storage is disabled')
    row=db.scalar(select(Document).where(Document.tenant_id==user.tenant_id,Document.id==document_id))
    if not row or row.status not in ('encrypted_dev_unscanned','scanned_private_s3'):raise HTTPException(404,'Document unavailable')
    patient=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==row.patient_id))
    if not patient:raise HTTPException(404,'Patient unavailable')
    require_consent(db,patient)
    if row.status=='scanned_private_s3':
        raw=s3_load(row.storage_key,user.tenant_id,row.id,row.sha256_hex or '')
    else:
        if not local_enabled():raise HTTPException(503,'Development store disabled')
        key=location(row.id,user.tenant_id)
        if not key.is_file():raise HTTPException(404,'Encrypted file missing')
        blob=key.read_bytes()
        try:raw=cipher().decrypt(blob[:12],blob[12:],(user.tenant_id+':'+row.id).encode())
        except Exception:raise HTTPException(500,'Integrity check failed')
    if row.sha256_hex and hashlib.sha256(raw).hexdigest()!=row.sha256_hex:
        raise HTTPException(500,'Document integrity check failed')
    mime=sniff(raw)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='dev_document_accessed',entity_type='Document',entity_id=row.id));db.commit()
    return Response(content=raw,media_type=mime,headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="document"','X-Content-Type-Options':'nosniff'})

@router.get('/cases/{case_id}/list')
def list_docs(case_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    c=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    rows=db.scalars(select(Document).where(Document.tenant_id==user.tenant_id,Document.case_id==case_id)).all()
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
    name=Path(file.filename or 'document').name.replace('\x00','')[:180]
    row=Document(tenant_id=grant.tenant_id,patient_id=p.id,case_id=c.id,filename=name,
        category='report',status='scanned_private_s3' if s3_ready() else 'encrypted_dev_unscanned',
        mime_type=mime,size_bytes=len(raw),sha256_hex=digest)
    db.add(row);db.flush()
    location_key=location(row.id,grant.tenant_id)
    try:
        if s3_ready():
            row.storage_key=s3_store(grant.tenant_id,row.id,raw,mime)
        else:
            nonce=secrets.token_bytes(12)
            blob=nonce+cipher().encrypt(nonce,raw,(grant.tenant_id+':'+row.id).encode())
            location_key.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with location_key.open('xb') as stream:stream.write(blob)
            os.chmod(location_key,0o600)
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
    rows=db.scalars(select(Document).where(Document.tenant_id==grant.tenant_id,Document.case_id==case_id)).all()
    return [{'id':d.id,'filename':d.filename,'status':d.status,'created_at':d.created_at} for d in rows]
