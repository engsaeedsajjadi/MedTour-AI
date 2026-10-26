"""Test-only FastAPI adapter for staged staff login, refresh and Meta routing.

Not registered by app.main. Never sends or stores a WhatsApp message.
Only the offline PostgreSQL clone probe installs this APIRouter.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .rate_limit import throttle
from .staged_preauth_service import StagedPreAuthService, MfaPending


class LoginPayload(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=250)
    password: str = Field(min_length=1, max_length=1024)


class MfaPayload(BaseModel):
    challenge_token: str = Field(min_length=48, max_length=300)
    code: str = Field(pattern=r"^[0-9]{6}$")


class RefreshPayload(BaseModel):
    refresh_token: str = Field(min_length=50, max_length=200)


def staged_preauth_router(service: StagedPreAuthService) -> APIRouter:
    if not isinstance(service, StagedPreAuthService):
        raise ValueError("Only a fully provisioned staged service can be mounted")
    router = APIRouter()

    @router.post("/api/v1/auth/login")
    def login(request: Request, body: LoginPayload, response: Response):
        response.headers["Cache-Control"] = "no-store, private"
        source = request.client.host if request.client else "unknown"
        throttle(source + ":" + body.tenant_slug + ":" + body.email.lower().strip())
        result = service.login(body.tenant_slug, body.email, body.password)
        if result is None:
            raise HTTPException(401, "Invalid credentials")
        if isinstance(result,MfaPending):
            response.status_code=202
            return {"mfa_required":True,
                "challenge_token":result.challenge_token,
                "expires_in":result.expires_in,
                "available_methods":["totp"],"access_token_issued":False}
        return {
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "token_type": "bearer",
            "role": result.role,
            "tenant_id": result.tenant_id,
        }

    @router.post("/api/v1/auth/mfa/verify")
    def verify(request:Request,body:MfaPayload,response:Response):
        response.headers["Cache-Control"]="no-store, private"
        source=request.client.host if request.client else "unknown"
        identifier=hashlib.sha256(body.challenge_token.encode()).hexdigest()
        throttle("mfa:"+source+":"+identifier,limit=10)
        result=service.verify_mfa(body.challenge_token,body.code)
        if result is None:
            raise HTTPException(401,"Invalid or expired MFA credential")
        return {"access_token":result.access_token,
            "refresh_token":result.refresh_token,"token_type":"bearer",
            "role":result.role,"tenant_id":result.tenant_id,"expires_in":1800}

    @router.post("/api/v1/auth/refresh")
    def refresh(request: Request, body: RefreshPayload):
        source = request.client.host if request.client else "unknown"
        # Never send a raw credential to the rate limiter/logs.
        identifier = hashlib.sha256(body.refresh_token.encode()).hexdigest()
        throttle("refresh:" + source + ":" + identifier, limit=15)
        result = service.refresh(body.refresh_token)
        if result is None:
            raise HTTPException(401, "Invalid refresh credential")
        return {
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "token_type": "bearer",
            "expires_in": 1800,
        }

    @router.post("/api/v1/webhooks/whatsapp")
    async def webhook(request: Request):
        raw = await request.body()
        if len(raw) > 262144:
            raise HTTPException(413, "Payload too large")
        routing = service.verify_webhook_route(
            raw, request.headers.get("X-Hub-Signature-256")
        )
        if routing is None:
            raise HTTPException(403, "Webhook signature or account not recognized")
        # Validated routing != processing approval. This adapter NEVER persists,
        # replies, extracts patient data, or forwards a request.
        return {
            "validated_only": True,
            "tenant_id": routing.tenant_id,
            "received": False,
            "processed_messages": 0,
            "auto_reply": False,
        }

    return router
