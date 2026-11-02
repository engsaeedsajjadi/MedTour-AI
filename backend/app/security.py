from __future__ import annotations
import os, hmac, hashlib, base64, secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .enterprise_models import RevokedAccess
from .tenant_context import bind_tenant

BEARER = HTTPBearer(auto_error=False)

def secret():
    s=os.getenv('JWT_SECRET','')
    if len(s)<32: raise RuntimeError('JWT_SECRET must contain at least 32 characters')
    return s

def password_hash(password:str)->str:
    if len(password)<12: raise ValueError('Password must be 12+ characters')
    salt=secrets.token_bytes(16)
    val=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600_000)
    return 'pbkdf2_sha256$600000$'+base64.urlsafe_b64encode(salt).decode()+'$'+base64.urlsafe_b64encode(val).decode()

def password_verify(password:str, stored:str)->bool:
    try:
        alg, n, salt, val=stored.split('$')
        if alg!='pbkdf2_sha256': return False
        sample=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.urlsafe_b64decode(salt),int(n))
        return hmac.compare_digest(sample,base64.urlsafe_b64decode(val))
    except (ValueError, TypeError): return False

def token_for(user:User,*,mfa_verified:bool=False):
    now=datetime.now(timezone.utc)
    return jwt.encode({'sub':user.id,'tid':user.tenant_id,'role':user.role,'iat':now,'exp':now+timedelta(minutes=30),'jti':secrets.token_urlsafe(12),'av':getattr(user,'auth_version',0),'mfa':mfa_verified},secret(),algorithm='HS256')

MFA_EXEMPT_PREFIXES=('/api/v1/auth/mfa/','/api/v1/auth/me','/api/v1/auth/logout','/api/v1/identity/mfa')

def staff_mfa_roles()->set[str]:
    """Roles that must use a second factor (default: admin and operator)."""
    configured={r.strip() for r in os.getenv('STAFF_MFA_ROLES','admin,operator').split(',') if r.strip()}
    # Production can widen the list but never drop the privileged roles.
    if os.getenv('APP_ENV','development')=='production':configured|={'admin','operator'}
    return configured

def staff_mfa_required(role:str|None=None)->bool:
    """Production always requires a second factor for privileged staff; other environments opt in."""
    enabled=os.getenv('APP_ENV','development')=='production' or os.getenv('STAFF_MFA_REQUIRED','').lower()=='true'
    return enabled and (role is None or role in staff_mfa_roles())

def _organization_requires_mfa(db,user)->bool:
    from .account_settings import organization_requires_mfa
    try:return organization_requires_mfa(db,user)
    except Exception:return False

def current_user(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(BEARER),db:Session=Depends(get_db)) -> User:
    if credentials is None: raise HTTPException(status_code=401,detail='Authentication required')
    try:
        data=jwt.decode(credentials.credentials, secret(), algorithms=['HS256'],options={'require':['exp','sub','tid','jti']})
        # Row-level security: from here on this request only sees its own tenant.
        bind_tenant(db,data['tid'])
        user=db.query(User).filter(User.id==data['sub'],User.tenant_id==data['tid'],User.active==True).first()
        if not user or user.role!=data.get('role') or user.auth_version!=data.get('av',0): raise ValueError('stale or invalid identity')
        from .staff_mfa import row_for
        legacy=row_for(db,user.tenant_id,user.id)
        if legacy and legacy.enabled and data.get('mfa') is not True:
            raise ValueError('Legacy MFA assurance required')
        revoked=db.query(RevokedAccess.id).filter(RevokedAccess.tenant_id==user.tenant_id,
            RevokedAccess.jti_hash==hashlib.sha256(data['jti'].encode()).hexdigest()).first()
        if revoked: raise ValueError('Access token has been revoked')
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status_code=401,detail='Invalid or expired token')
    if data.get('mfa') is not True and not request.url.path.startswith(MFA_EXEMPT_PREFIXES) and (
            staff_mfa_required(user.role) or _organization_requires_mfa(db,user)):
        # Signed in with a password only: allow enrolment/verification of the second factor, nothing else.
        raise HTTPException(status_code=403,detail='Two-factor authentication required')
    return user

def roles(*allowed):
    def require(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        if user.role not in allowed:
            from .security_audit import record
            route=request.scope.get('route')
            path=getattr(route,'path',None) or request.url.path
            record(db,tenant_id=user.tenant_id,user_id=user.id,event='access_denied',
                entity_type='Endpoint',entity_id=user.id,detail=f'{request.method} {path} role={user.role}')
            raise HTTPException(status_code=403,detail='Permission denied')
        return user
    return require
