"""Rotatable refresh tokens and access-token revocation for authenticated staff."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import secrets,hashlib,jwt
from fastapi import APIRouter,Depends,HTTPException,Header
from pydantic import BaseModel,Field
from sqlalchemy import select,update
from sqlalchemy.orm import Session
from .database import get_db
from .security import current_user,token_for,secret
from .models import User,Audit
from .enterprise_models import RefreshSession,RevokedAccess

router=APIRouter(prefix='/api/v1/auth',tags=['staff sessions'])

def hash_token(raw:str):return hashlib.sha256(raw.encode()).hexdigest()

def issue_refresh(db:Session,user:User):
    raw=secrets.token_urlsafe(48)
    session=RefreshSession(tenant_id=user.tenant_id,user_id=user.id,refresh_hash=hash_token(raw),
        family_id=str(__import__('uuid').uuid4()),expires_at=datetime.now(timezone.utc)+timedelta(days=7))
    db.add(session);db.commit()
    return raw

class RefreshIn(BaseModel):
    refresh_token:str=Field(min_length=50,max_length=200)

@router.post('/refresh')
def refresh(body:RefreshIn,db:Session=Depends(get_db)):
    previous=db.scalar(select(RefreshSession).where(RefreshSession.refresh_hash==hash_token(body.refresh_token)).with_for_update())
    if not previous:raise HTTPException(401,'Invalid refresh credential')
    # A reused refresh token invalidates the entire family; never reactivate a session.
    if previous.revoked_at is not None:
        db.execute(update(RefreshSession).where(RefreshSession.family_id==previous.family_id).values(revoked_at=datetime.now(timezone.utc)))
        db.commit();raise HTTPException(401,'Refresh replay detected')
    expiration=previous.expires_at
    if expiration.tzinfo is None:expiration=expiration.replace(tzinfo=timezone.utc)
    if expiration<=datetime.now(timezone.utc):raise HTTPException(401,'Refresh expired')
    user=db.scalar(select(User).where(User.tenant_id==previous.tenant_id,User.id==previous.user_id,User.active==True))
    if not user:raise HTTPException(401,'Account disabled')
    now=datetime.now(timezone.utc)
    previous.revoked_at=now;previous.last_rotated_at=now
    raw=secrets.token_urlsafe(48)
    newer=RefreshSession(tenant_id=user.tenant_id,user_id=user.id,refresh_hash=hash_token(raw),
        family_id=previous.family_id,expires_at=now+timedelta(days=7))
    db.add(newer);db.commit()
    return {'access_token':token_for(user,mfa_verified=True),'refresh_token':raw,'token_type':'bearer','expires_in':1800}

@router.post('/logout')
def logout(authorization:str|None=Header(None),user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Bearer required')
    claims=jwt.decode(authorization[7:],secret(),algorithms=['HS256'])
    record=RevokedAccess(tenant_id=user.tenant_id,user_id=user.id,
        jti_hash=hash_token(claims['jti']),expires_at=datetime.fromtimestamp(claims['exp'],tz=timezone.utc))
    db.add(record)
    db.execute(update(RefreshSession).where(RefreshSession.tenant_id==user.tenant_id,
        RefreshSession.user_id==user.id,RefreshSession.revoked_at==None).values(revoked_at=datetime.now(timezone.utc)))
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event='staff_logout',entity_type='User',entity_id=user.id))
    db.commit();return {'logged_out':True}
