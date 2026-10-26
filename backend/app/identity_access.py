"""Section 27: TOTP + scoped identity lifecycle; synthetic healthcare alpha.

TOTP secrets encrypted at rest with mandatory independent AES-256-GCM key.
Never email MFA secrets, put challenge credentials in logs or issue JWT after
password-only login to an enrolled account.
"""
from __future__ import annotations
import base64,hashlib,hmac,os,secrets,struct,time,re,uuid
from datetime import datetime,timezone,timedelta
from urllib.parse import quote
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,update,func
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Audit
from .enterprise_models import StaffTotp,StaffMfaChallenge,RefreshSession
from .security import current_user,roles,token_for,password_verify
from .session_api import issue_refresh,hash_token

router=APIRouter(prefix="/api/v1/auth",tags=["staff MFA"])
admin=roles("admin")
MFA_TTL=300
ATTEMPTS=5

def now():return datetime.now(timezone.utc)
def utc(dt):return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
def encryption_key():
    raw=os.getenv("MFA_ENCRYPTION_KEY","")
    try:key=base64.urlsafe_b64decode(raw+"="*((-len(raw))%4))
    except (ValueError,TypeError):key=b""
    if len(key)!=32:raise HTTPException(503,"Independent MFA secret encryption key is not configured")
    return key

def seal(secret:str,tenant_id:str,user_id:str):
    key=encryption_key()
    nonce=secrets.token_bytes(12)
    data=AESGCM(key).encrypt(nonce,secret.encode(),(tenant_id+":"+user_id).encode())
    return base64.urlsafe_b64encode(nonce+data).decode()

def open_secret(row:StaffTotp):
    try:
        data=base64.urlsafe_b64decode(row.encrypted_secret)
        clear=AESGCM(encryption_key()).decrypt(data[:12],data[12:],
            (row.tenant_id+":"+row.user_id).encode())
        return clear.decode()
    except (ValueError,TypeError,UnicodeDecodeError) as exc:
        raise HTTPException(503,"MFA secret unavailable") from exc
    except Exception as exc:
        if isinstance(exc,HTTPException):raise
        raise HTTPException(503,"MFA secret decryption failed") from exc

def code_for(secret:str,step:int):
    raw=base64.b32decode(secret,casefold=True)
    digest=hmac.new(raw,struct.pack(">Q",step),hashlib.sha1).digest()
    idx=digest[-1]&15
    return f"{(int.from_bytes(digest[idx:idx+4],'big')&0x7fffffff)%1000000:06d}"

def accepted_step(secret:str,code:str,last_step:int,at:int|None=None):
    if not isinstance(code,str) or not re.fullmatch(r"[0-9]{6}",code):return None
    timestamp=int(time.time() if at is None else at)
    current=timestamp//30
    for step in (current-1,current,current+1):
        if step<=last_step:continue
        if hmac.compare_digest(code_for(secret,step),code):return step
    return None

def invalidate_sessions(db:Session,user:User):
    db.execute(update(RefreshSession).where(RefreshSession.tenant_id==user.tenant_id,
        RefreshSession.user_id==user.id,RefreshSession.revoked_at.is_(None)).values(revoked_at=now()))
    user.auth_version+=1
    db.execute(update(StaffMfaChallenge).where(
        StaffMfaChallenge.tenant_id==user.tenant_id,
        StaffMfaChallenge.user_id==user.id,
        StaffMfaChallenge.used_at.is_(None)).values(used_at=now()))

def tokens(db,user):
    access=token_for(user)
    signer=db.info.get("tenant_route_keyring")
    if signer:
        # In strict tenant-role mode the refresh token MUST carry an
        # authenticated tenant routing hint before opening any DB connection.
        refresh=signer.issue(purpose="refresh",tenant_id=user.tenant_id,
            ttl_seconds=7*86400)
        db.add(RefreshSession(tenant_id=user.tenant_id,user_id=user.id,
            refresh_hash=hash_token(refresh),family_id=str(uuid.uuid4()),
            expires_at=now()+timedelta(days=7)))
        db.commit()
    else:
        refresh=issue_refresh(db,user)
    return {"access_token":access,"refresh_token":refresh,"token_type":"bearer",
            "role":user.role,"tenant_id":user.tenant_id}

def require_bound_physician(db,user):
    if user.role!="physician":return
    from .enterprise_models import PhysicianAccount
    bound=db.scalar(select(PhysicianAccount.id).where(
        PhysicianAccount.tenant_id==user.tenant_id,
        PhysicianAccount.user_id==user.id,PhysicianAccount.active.is_(True)))
    if not bound:raise HTTPException(403,"Physician identity must be bound to its own active account")

def password_login(db:Session,user:User):
    factor=db.scalar(select(StaffTotp).where(
        StaffTotp.tenant_id==user.tenant_id,StaffTotp.user_id==user.id))
    if not factor or not factor.enabled:return None
    encryption_key() # Fail closed before issuing even a challenge.
    raw=secrets.token_urlsafe(48)
    db.add(StaffMfaChallenge(tenant_id=user.tenant_id,user_id=user.id,
        challenge_hash=hash_token(raw),auth_version=user.auth_version,
        expires_at=now()+timedelta(seconds=MFA_TTL),attempts=0))
    db.commit()
    return {"mfa_required":True,"challenge_token":raw,"expires_in":MFA_TTL,
            "available_methods":["totp"],"access_token_issued":False}

@router.get("/mfa/status")
def status(db:Session=Depends(get_db),user:User=Depends(current_user)):
    x=db.scalar(select(StaffTotp).where(StaffTotp.tenant_id==user.tenant_id,
        StaffTotp.user_id==user.id))
    return {"enabled":bool(x and x.enabled),"enrollment_pending":bool(x and not x.enabled),
        "method":"totp","recovery_codes_configured":False,
        "independently_verified_identity":False}

@router.post("/mfa/enroll")
def enroll(response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    response.headers["Cache-Control"]="no-store, private"
    response.headers["Pragma"]="no-cache"
    encryption_key()
    db.scalar(select(User.id).where(User.id==user.id,User.tenant_id==user.tenant_id).with_for_update())
    row=db.scalar(select(StaffTotp).where(StaffTotp.tenant_id==user.tenant_id,
        StaffTotp.user_id==user.id).with_for_update())
    if row and row.enabled:raise HTTPException(409,"MFA already enabled")
    secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    if row:
        row.encrypted_secret=seal(secret,user.tenant_id,user.id)
        row.setup_expires_at=now()+timedelta(minutes=10);row.last_step=-1
    else:
        db.add(StaffTotp(tenant_id=user.tenant_id,user_id=user.id,
            encrypted_secret=seal(secret,user.tenant_id,user.id),
            enabled=False,setup_expires_at=now()+timedelta(minutes=10),last_step=-1))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="mfa_enrollment_started",entity_type="User",entity_id=user.id))
    db.commit()
    label=quote("MedTour:"+user.email,safe="")
    return {"secret":secret,
        "otpauth_uri":f"otpauth://totp/{label}?secret={secret}&issuer=MedTour&period=30&digits=6",
        "expires_in":600,"shared_secret_displayed_once":True}

class CodeIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    code:str=Field(pattern=r"^[0-9]{6}$")

@router.post("/mfa/confirm")
def confirm(body:CodeIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    db.scalar(select(User.id).where(User.tenant_id==user.tenant_id,
        User.id==user.id).with_for_update())
    row=db.scalar(select(StaffTotp).where(StaffTotp.tenant_id==user.tenant_id,
        StaffTotp.user_id==user.id).with_for_update())
    if not row or row.enabled or utc(row.setup_expires_at)<now():
        raise HTTPException(409,"MFA enrollment not pending")
    step=accepted_step(open_secret(row),body.code,row.last_step)
    if step is None:raise HTTPException(401,"Invalid verification code")
    row.enabled=True;row.last_step=step
    invalidate_sessions(db,user)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="mfa_enabled",entity_type="User",entity_id=user.id))
    db.flush()
    return {"enabled":True,**tokens(db,user)}

class VerifyIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    challenge_token:str=Field(min_length=48,max_length=200)
    code:str=Field(pattern=r"^[0-9]{6}$")

@router.post("/mfa/verify")
def verify(body:VerifyIn,response:Response,db:Session=Depends(get_db)):
    response.headers["Cache-Control"]="no-store, private"
    challenge=db.scalar(select(StaffMfaChallenge).where(
        StaffMfaChallenge.challenge_hash==hash_token(body.challenge_token)).with_for_update())
    if challenge is None:raise HTTPException(401,"Invalid MFA challenge")
    user=db.scalar(select(User).where(User.tenant_id==challenge.tenant_id,
        User.id==challenge.user_id,User.active.is_(True)).with_for_update())
    if user is None or user.auth_version!=challenge.auth_version:
        raise HTTPException(401,"Invalid or stale MFA challenge")
    if challenge.used_at or challenge.attempts>=ATTEMPTS or utc(challenge.expires_at)<=now():
        raise HTTPException(401,"MFA challenge expired or exhausted")
    factor=db.scalar(select(StaffTotp).where(
        StaffTotp.tenant_id==user.tenant_id,
        StaffTotp.user_id==user.id,StaffTotp.enabled.is_(True)).with_for_update())
    if not factor:raise HTTPException(401,"MFA no longer available")
    challenge.attempts+=1
    step=accepted_step(open_secret(factor),body.code,factor.last_step)
    if step is None:
        if challenge.attempts>=ATTEMPTS:challenge.used_at=now()
        db.commit()
        raise HTTPException(401,"Invalid MFA code")
    factor.last_step=step
    challenge.used_at=now()
    db.execute(update(StaffMfaChallenge).where(
        StaffMfaChallenge.tenant_id==user.tenant_id,
        StaffMfaChallenge.user_id==user.id,
        StaffMfaChallenge.used_at.is_(None)).values(used_at=now()))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="mfa_login_succeeded",entity_type="User",entity_id=user.id))
    db.flush()
    return tokens(db,user)

class PasswordIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    current_password:str=Field(min_length=1,max_length=1024)
    new_password:str=Field(min_length=16,max_length=1024)

@router.post("/password/change")
def change_password(body:PasswordIn,db:Session=Depends(get_db),
                    user:User=Depends(current_user)):
    from .security import password_hash
    db.scalar(select(User.id).where(User.tenant_id==user.tenant_id,
        User.id==user.id).with_for_update())
    if not password_verify(body.current_password,user.password_hash):
        raise HTTPException(401,"Invalid current credential")
    if body.current_password==body.new_password:raise HTTPException(422,"New password must differ")
    user.password_hash=password_hash(body.new_password)
    invalidate_sessions(db,user)
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="staff_password_changed",entity_type="User",entity_id=user.id))
    db.commit()
    return {"changed":True,"sessions_revoked":True,"login_required":True}

class AccountChange(BaseModel):
    model_config=ConfigDict(extra="forbid")
    active:bool

@router.get("/staff")
def list_staff(db:Session=Depends(get_db),user:User=Depends(admin)):
    rows=db.scalars(select(User).where(User.tenant_id==user.tenant_id).limit(250)).all()
    return {"items":[{"id":x.id,"email":x.email,"role":x.role,
        "active":x.active,"auth_version":x.auth_version} for x in rows]}

@router.put("/staff/{staff_id}/active")
def staff_active(staff_id:str,body:AccountChange,
                db:Session=Depends(get_db),actor:User=Depends(admin)):
    target=db.scalar(select(User).where(User.tenant_id==actor.tenant_id,
        User.id==staff_id).with_for_update())
    if not target:raise HTTPException(404,"Staff account not found")
    if target.id==actor.id and not body.active:
        raise HTTPException(409,"Cannot disable your own admin login")
    if target.role=="admin" and not body.active:
        admins=db.scalar(select(func.count()).select_from(User).where(
            User.tenant_id==actor.tenant_id,
            User.role=="admin",User.active.is_(True)))
        if admins<=1:raise HTTPException(409,"Cannot disable last active admin")
    if target.active!=body.active:
        target.active=body.active
        invalidate_sessions(db,target)
        db.add(Audit(tenant_id=actor.tenant_id,user_id=actor.id,
            event="staff_account_state_changed",entity_type="User",entity_id=target.id))
        db.commit()
    return {"id":target.id,"active":target.active,"all_prior_sessions_invalidated":True}

class RoleChange(BaseModel):
    model_config=ConfigDict(extra="forbid")
    role:Literal["operator","physician","auditor","hospital"]

@router.put("/staff/{staff_id}/role")
def staff_role(staff_id:str,body:RoleChange,db:Session=Depends(get_db),
               actor:User=Depends(admin)):
    # Intentionally no admin grants or reassignments via this endpoint.
    # Organization super-admin provisioning needs stronger independent identity
    # proof and should not be self-service in the current alpha.
    target=db.scalar(select(User).where(
        User.tenant_id==actor.tenant_id,User.id==staff_id).with_for_update())
    if not target:raise HTTPException(404,"Staff account not found")
    if target.id==actor.id or target.role=="admin":
        raise HTTPException(409,"Admin role changes require an independent owner workflow")
    if target.role!=body.role:
        target.role=body.role
        invalidate_sessions(db,target)
        db.add(Audit(tenant_id=actor.tenant_id,user_id=actor.id,
            event="staff_role_changed",entity_type="User",entity_id=target.id))
        db.commit()
    return {"id":target.id,"role":target.role,"sessions_revoked":True,
            "physician_binding_required":target.role=="physician",
            "clinical_privileges_granted":False}
