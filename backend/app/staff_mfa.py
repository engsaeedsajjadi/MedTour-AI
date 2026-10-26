"""RFC 6238 SHA-1 TOTP, AES-GCM at rest, one-time counter replay protection.

Enrollment is explicitly initiated by an authenticated staff member; a
password-only session remains possible until the member confirms the code.
"""
from __future__ import annotations
import base64,hashlib,hmac,os,secrets,struct,time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .enterprise_models import StaffMFA

PERIOD=30

def key():
    raw=os.getenv("STAFF_MFA_ENCRYPTION_KEY","")
    try:decoded=base64.urlsafe_b64decode(raw+"="*(-len(raw)%4))
    except (ValueError,TypeError) as e:raise RuntimeError("Invalid MFA encryption key") from e
    if len(decoded)!=32:raise RuntimeError("STAFF_MFA_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return decoded

def encrypted(secret:bytes,tenant_id:str,user_id:str)->str:
    nonce=secrets.token_bytes(12)
    aad=(tenant_id+":"+user_id).encode()
    return base64.urlsafe_b64encode(nonce+AESGCM(key()).encrypt(nonce,secret,aad)).decode()

def decrypted(row:StaffMFA)->bytes:
    data=base64.urlsafe_b64decode(row.secret_encrypted)
    return AESGCM(key()).decrypt(data[:12],data[12:],(row.tenant_id+":"+row.user_id).encode())

def totp(secret:bytes,counter:int)->str:
    mac=hmac.new(secret,struct.pack(">Q",counter),hashlib.sha1).digest()
    pos=mac[-1]&15
    value=(struct.unpack(">I",mac[pos:pos+4])[0]&0x7fffffff)%1000000
    return f"{value:06d}"

def row_for(db:Session,tenant_id:str,user_id:str,lock=False):
    q=select(StaffMFA).where(StaffMFA.tenant_id==tenant_id,StaffMFA.user_id==user_id)
    return db.scalar(q.with_for_update() if lock else q)

def verify(db:Session,user,code:str|None,*,require_if_enabled=True)->bool:
    row=row_for(db,user.tenant_id,user.id,True)
    if not row or not row.enabled:
        return not require_if_enabled or not row or not row.enabled
    if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdecimal():
        return False
    try:secret=decrypted(row)
    except (ValueError,KeyError):return False
    current=int(time.time()//PERIOD)
    for counter in (current-1,current,current+1):
        if counter>row.last_counter and hmac.compare_digest(totp(secret,counter),code):
            row.last_counter=counter
            db.flush()
            return True
    return False

def ensure_enrolled_gate(db:Session,user,code:str|None):
    if not verify(db,user,code):
        raise HTTPException(401,"Invalid credentials or MFA verification")
