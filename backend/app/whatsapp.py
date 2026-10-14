"""WhatsApp official Cloud API webhook scaffold; incoming content is never accepted unprocessed."""
from __future__ import annotations
import os,hmac,hashlib
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse

router=APIRouter(prefix='/api/v1/webhooks/whatsapp',tags=['WhatsApp — disabled by default'])

def enabled():
    return os.getenv('WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED','').lower()=='true' and bool(os.getenv('META_APP_SECRET')) and bool(os.getenv('META_VERIFY_TOKEN'))

def valid_signature(payload:bytes, header:str|None, secret:str)->bool:
    if not header or not header.startswith('sha256=') or len(header)!=71:return False
    expected='sha256='+hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,header)

@router.get('',response_class=PlainTextResponse)
async def challenge(
    mode:str|None=Query(None,alias='hub.mode'),
    token:str|None=Query(None,alias='hub.verify_token'),
    challenge_value:str|None=Query(None,alias='hub.challenge')):
    if not enabled():raise HTTPException(503,'WhatsApp integration disabled pending official eligibility')
    if mode!='subscribe' or not token or not hmac.compare_digest(token,os.environ['META_VERIFY_TOKEN']):
        raise HTTPException(403,'Invalid verification token')
    return challenge_value or ''

@router.post('')
async def receive(request:Request):
    if not enabled():raise HTTPException(503,'WhatsApp integration disabled pending official eligibility')
    raw=await request.body()
    if len(raw)>262144:raise HTTPException(413,'Payload too large')
    if not valid_signature(raw,request.headers.get('X-Hub-Signature-256'),os.environ['META_APP_SECRET']):
        raise HTTPException(403,'Invalid Meta signature')
    # Fail closed: do NOT return 200 and lose an inbound message before durable queue,
    # idempotency, contact consent/retention policy and tenant routing are implemented.
    raise HTTPException(503,'Durable WhatsApp processing pipeline is not activated')
