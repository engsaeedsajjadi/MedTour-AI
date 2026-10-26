"""Controlled synthetic-only full-route tenant-principal ASGI cutover pilot.

Unlike the 19.20 partial router, this adapter evaluates EVERY FastAPI DB
dependency through a trusted tenant DB role. Staff routes use verified JWT,
public routes use a server-provisioned slug, patient/consent routes use
purpose-bound MAC tokens, login/refresh use the staged pre-auth service, and
Meta messages require verified official HMAC before opening a tenant session.
Unknown pre-auth flows return 401/503, never a privileged connection.
Production credentials and real PHI are NOT authorized by this pilot.
"""
from __future__ import annotations
import hashlib,json,os,re
from collections.abc import Mapping
from contextlib import contextmanager
from uuid import UUID
import jwt
from fastapi import FastAPI,Request,HTTPException
from sqlalchemy import text,select
from sqlalchemy.exc import SQLAlchemyError
from .database import get_db
from .security import secret
from .models import User
from .enterprise_models import PortalLoginChallenge
from .staged_epoch_preauth_bridge import EpochGuardedSessionFactory
from .staged_tenant_epoch_control import StagedCoordinatedTenantRegistry
from .staged_tenant_pool_registry import TenantPrincipalConfig
from .tenant_route_tokens import TenantRouteKeyring,token_sha256
from .tenant_credential_lookup import TenantCredentialLookup
from .staged_preauth_service import StagedPreAuthService
from .staged_preauth_http import staged_preauth_router

_PUBLIC=re.compile(r"^/api/v1/public/([a-z0-9][a-z0-9-]{0,99})(?:/.*)?$")
_BEARER=re.compile(r"^Bearer ([^\s]{1,4096})$")
_PREAUTH={"/api/v1/auth/login","/api/v1/auth/refresh"}
_PORTAL_PREFIX="/api/v1/portal/"
_CONSENT_PREFIX="/api/v1/consent-links/"
_META="/api/v1/webhooks/whatsapp"

def _canonical(value)->bool:
    if not isinstance(value,str) or len(value)!=36:return False
    try:return str(UUID(value))==value
    except (ValueError,TypeError,AttributeError):return False

class StrictTenantGateway:
    def __init__(self,*,registry:StagedCoordinatedTenantRegistry,
                 provisioned:Mapping[str,TenantPrincipalConfig],
                 keyring:TenantRouteKeyring,meta_app_secret:str,
                 whatsapp_approved:bool=False):
        if (os.getenv("APP_ENV")!="test" or os.getenv("DATABASE_URL")!="sqlite://"
            or os.getenv("MEDTOUR_SYNTHETIC_CLONE")!="1"):
            raise RuntimeError("Strict tenant gateway pilot limited to synthetic clone")
        if not isinstance(registry,StagedCoordinatedTenantRegistry) or not isinstance(keyring,TenantRouteKeyring):
            raise ValueError("Trusted registry and independent MAC keyring required")
        if not isinstance(provisioned,Mapping) or not 1<=len(provisioned)<=16:
            raise ValueError("Pre-provisioned tenants required")
        self.registry=registry;self.keyring=keyring
        self.slugs={};self.phones={};self.sessions={}
        for tid,config in provisioned.items():
            if not isinstance(config,TenantPrincipalConfig) or tid!=config.tenant_id or not _canonical(tid):
                raise ValueError("Invalid trusted tenant configuration")
            if config.slug in self.slugs or config.whatsapp_phone_id in self.phones:
                raise ValueError("Duplicate trusted tenant slug or provider account")
            self.slugs[config.slug]=tid;self.phones[config.whatsapp_phone_id]=tid
            self.sessions[tid]=EpochGuardedSessionFactory(registry,tid)
        self.service=StagedPreAuthService(
            keyring=keyring,sessions_by_tenant=self.sessions,
            tenant_slugs=self.slugs,whatsapp_accounts=self.phones,
            whatsapp_app_secret=meta_app_secret,whatsapp_approved=whatsapp_approved)
        self.credentials=TenantCredentialLookup(keyring=keyring,
            sessions_by_tenant=self.sessions)
        from .main import app as inner_app
        self.app=inner_app
        if get_db in inner_app.dependency_overrides:
            raise RuntimeError("Another DB override is already installed")
        inner_app.dependency_overrides[get_db]=self.get_db
        self.preauth=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        for route in staged_preauth_router(self.service).routes:
            if route.path in _PREAUTH:self.preauth.router.routes.append(route)

    def close(self):
        self.app.dependency_overrides.pop(get_db,None)
        self.registry.close()

    async def __call__(self,scope,receive,send):
        if scope.get("type")!="http":
            await self.app(scope,receive,send);return
        method=scope.get("method")
        path=scope.get("path","")
        if path in _PREAUTH and method=="POST":
            await self.preauth(scope,receive,send);return
        if path in _PREAUTH or path==_META and method not in ("POST","GET"):
            # Method mismatch never reaches legacy pre-auth.
            from starlette.responses import JSONResponse
            await JSONResponse({"detail":"Unsupported pre-auth method"},status_code=405)(scope,receive,send)
            return
        await self.app(scope,receive,send)

    def _jwt_tenant(self,request:Request)->str|None:
        m=_BEARER.fullmatch(request.headers.get("authorization",""))
        if not m:return None
        try:
            claims=jwt.decode(m.group(1),secret(),algorithms=["HS256"],
               options={"require":["exp","sub","tid","role","jti"]})
        except jwt.PyJWTError:
            raise HTTPException(401,"Invalid signed staff credential")
        tid=claims.get("tid")
        if not _canonical(tid) or not all(isinstance(claims.get(x),str) for x in ("sub","role","jti")):
            raise HTTPException(401,"Invalid staff tenant identity")
        return tid

    def _verified_hint(self,token,purpose):
        hint=self.keyring.verify(token,expected_purpose=purpose)
        if not hint or hint.tenant_id not in self.sessions:
            raise HTTPException(401,"Invalid or unrouteable tenant credential")
        return hint.tenant_id

    async def _resolve(self,request:Request):
        path=request.url.path
        if path in _PREAUTH:
            raise HTTPException(503,"Pre-auth must use restricted gateway handler")
        if path==_META and request.method=="POST":
            raw=await request.body()
            routing=self.service.verify_webhook_route(raw,
                request.headers.get("x-hub-signature-256"))
            if not routing:raise HTTPException(403,"Invalid Meta signature or tenant route")
            return routing.tenant_id,None
        staff=self._jwt_tenant(request)
        if staff:
            return staff,None
        match=_PUBLIC.fullmatch(path)
        if match:
            slug=match.group(1)
            tid=self.slugs.get(slug)
            if not tid:raise HTTPException(404,"Public tenant not found")
            return tid,slug
        if path.startswith(_PORTAL_PREFIX):
            if path=="/api/v1/portal/session/exchange":
                try:body=await request.json()
                except (ValueError,UnicodeDecodeError):raise HTTPException(401,"Invalid invitation")
                token=body.get("invitation_token") if isinstance(body,dict) else None
                tid=self._verified_hint(token,"portal")
                # Full invitation hash/expiry/one-time proof still checked in
                # the existing exchange endpoint; no global credential search.
                return tid,None
            token=request.headers.get("x-patient-access")
            tid=self._verified_hint(token,"portal")
            if self.credentials.lookup(token,purpose="portal") is None:
                raise HTTPException(401,"Unverified patient access")
            return tid,None
        if path.startswith(_CONSENT_PREFIX) and path.endswith(("/preview","/respond")):
            if path.endswith("/preview"):
                token=request.query_params.get("token")
            else:
                try:body=await request.json()
                except (ValueError,UnicodeDecodeError):raise HTTPException(401,"Invalid consent")
                token=body.get("token") if isinstance(body,dict) else None
            tid=self._verified_hint(token,"consent")
            if self.credentials.lookup(token,purpose="consent") is None:
                raise HTTPException(401,"Unverified consent credential")
            return tid,None
        # Health ready and any undocumented anonymous endpoints cannot borrow
        # a superuser, public tenant or another request's role.
        raise HTTPException(401,"Authenticated tenant route required")

    @staticmethod
    def _prove_connection(db,tid):
        # Cross-check actual PostgreSQL login, protected role mapping, and
        # table-wide FORCE RLS rather than trusting an HTTP-supplied GUC.
        if db.bind is None or db.bind.dialect.name!="postgresql":
            raise HTTPException(503,"Restricted PostgreSQL required")
        row=db.execute(text("""
            SELECT session_user::text,current_user::text,
                   medtour_principal_private.tenant_for_login()::text,
                   r.rolsuper,r.rolbypassrls,r.rolcreaterole
            FROM pg_roles r WHERE r.rolname=session_user
        """)).one()
        if row[0]!=row[1] or row[2]!=tid or any(row[3:]):
            raise HTTPException(503,"Tenant database role mismatch")
        total,protected=db.execute(text("""
            SELECT count(*),count(*) FILTER(WHERE c.relrowsecurity AND c.relforcerowsecurity)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id'
            WHERE n.nspname='public' AND c.relkind='r'
              AND a.attnum>0 AND NOT a.attisdropped
        """)).one()
        if total<80 or total!=protected:
            raise HTTPException(503,"Tenant database RLS policy coverage incomplete")

    async def get_db(self,request:Request):
        tid,slug=await self._resolve(request)
        try:
            with self.registry.acquire_tenant(tid) as lease:
                with lease.session() as db:
                    self._prove_connection(db,tid)
                    db.info["verified_tenant_id"]=tid
                    if slug:db.info["verified_public_slug"]=slug
                    db.info["tenant_route_keyring"]=self.keyring
                    yield db
        except HTTPException:raise
        except (SQLAlchemyError,LookupError,PermissionError):
            raise HTTPException(503,"Restricted tenant database unavailable") from None
