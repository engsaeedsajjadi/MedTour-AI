"""Private encrypted development uploads; production requires independently audited object storage + malware scan."""
from __future__ import annotations
import hashlib,os,base64,secrets
from pathlib import Path
from io import BytesIO
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .models import User,Case,Patient,Consent,Document,Audit
from .database import get_db
from .security import roles

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
    for mime,header in MIMES.items():
        if data.startswith(header):return mime
    raise HTTPException(415,'Only signed PDF/JPEG/PNG contents are allowed')

@router.post('/cases/{case_id}',status_code=201)
async def upload(case_id:str,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    if not local_enabled():raise HTTPException(503,'Production medical file storage and malware scanner are not configured')
    c=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==c.patient_id))
    require_consent(db,p)
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise HTTPException(413,'Document exceeds 8 MiB')
    if not raw:raise HTTPException(422,'Empty document')
    mime=sniff(raw)
    # This is an EXPLICIT DEVELOPMENT-ONLY path. No production ClamAV/object storage claims.
    name=Path(file.filename or 'file').name.replace('\x00','')[:180]
    row=Document(tenant_id=user.tenant_id,patient_id=p.id,case_id=c.id,filename=name,
        category='report',status='encrypted_dev_unscanned')
    db.add(row);db.flush()
    key=location(row.id,user.tenant_id)
    blob=secrets.token_bytes(12)
    encrypted=blob+cipher().encrypt(blob,raw,(user.tenant_id+':'+row.id).encode())
    key.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    try:
        with key.open('xb') as stream:stream.write(encrypted)
        os.chmod(key,0o600)
        row.storage_key=row.id+'.enc'
        db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='dev_encrypted_document_uploaded',entity_type='Document',entity_id=row.id))
        db.commit()
    except Exception:
        db.rollback();key.unlink(missing_ok=True);raise
    return {'id':row.id,'status':row.status,'mime_type':mime,'byte_length':len(raw),'production_approved':False}

@router.get('/{document_id}')
def download(document_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    if not local_enabled():raise HTTPException(503,'Development encrypted storage is disabled')
    row=db.scalar(select(Document).where(Document.tenant_id==user.tenant_id,Document.id==document_id))
    if not row or row.status!='encrypted_dev_unscanned':raise HTTPException(404,'Document unavailable')
    key=location(row.id,user.tenant_id)
    if not key.is_file():raise HTTPException(404,'Encrypted file missing')
    blob=key.read_bytes()
    try:raw=cipher().decrypt(blob[:12],blob[12:],(user.tenant_id+':'+row.id).encode())
    except Exception:raise HTTPException(500,'Integrity check failed')
    mime=sniff(raw)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='dev_document_accessed',entity_type='Document',entity_id=row.id));db.commit()
    return Response(content=raw,media_type=mime,headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="document"','X-Content-Type-Options':'nosniff'})

@router.get('/cases/{case_id}/list')
def list_docs(case_id:str,db:Session=Depends(get_db),user:User=Depends(roles('admin','operator'))):
    c=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==case_id))
    if not c:raise HTTPException(404,'Case not found')
    rows=db.scalars(select(Document).where(Document.tenant_id==user.tenant_id,Document.case_id==case_id)).all()
    return [{'id':x.id,'filename':x.filename,'status':x.status,'category':x.category,'created_at':x.created_at} for x in rows]
