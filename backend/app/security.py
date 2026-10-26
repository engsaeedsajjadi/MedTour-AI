from __future__ import annotations
import os, hmac, hashlib, base64, secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .enterprise_models import RevokedAccess

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

def token_for(user:User):
    now=datetime.now(timezone.utc)
    return jwt.encode({'sub':user.id,'tid':user.tenant_id,'role':user.role,'iat':now,'exp':now+timedelta(minutes=30),'jti':secrets.token_urlsafe(12),'av':getattr(user,'auth_version',0)},secret(),algorithm='HS256')

def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(BEARER),db:Session=Depends(get_db)) -> User:
    if credentials is None: raise HTTPException(status_code=401,detail='Authentication required')
    try:
        data=jwt.decode(credentials.credentials, secret(), algorithms=['HS256'],options={'require':['exp','sub','tid','jti']})
        user=db.query(User).filter(User.id==data['sub'],User.tenant_id==data['tid'],User.active==True).first()
        if not user or user.role!=data.get('role') or user.auth_version!=data.get('av',0): raise ValueError('stale or invalid identity')
        if user.role=="physician":
            from .enterprise_models import PhysicianAccount
            link=db.query(PhysicianAccount.id).filter(
                PhysicianAccount.tenant_id==user.tenant_id,
                PhysicianAccount.user_id==user.id,
                PhysicianAccount.active.is_(True)).first()
            if not link:raise HTTPException(403,'Physician identity is not linked to an active account')
        revoked=db.query(RevokedAccess.id).filter(RevokedAccess.tenant_id==user.tenant_id,
            RevokedAccess.jti_hash==hashlib.sha256(data['jti'].encode()).hexdigest()).first()
        if revoked: raise ValueError('Access token has been revoked')
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status_code=401,detail='Invalid or expired token')

def roles(*allowed):
    def require(user:User=Depends(current_user)):
        if user.role not in allowed: raise HTTPException(status_code=403,detail='Permission denied')
        return user
    return require
