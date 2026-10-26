"""Section 25: synthetic, bounded voice messaging STT/TTS and manual review.

No case, patient, conversation or external-channel integration. Audio and
recognized words are NOT persisted in database, object storage or logs.
"""
from __future__ import annotations
import hashlib,os,re
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile,Response
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Tenant,Audit
from .enterprise_models import VoiceSampleJob
from .security import roles
from .rate_limit import throttle
from .receptionist import RESPONSES
from .voice_processing import MAX_INPUT_BYTES,decode_voice
from .voice_provider import readiness,transcribe as provider_transcribe,synthesize as provider_synthesize

router=APIRouter(prefix="/voice",tags=["synthetic voice messaging"])
STAFF=roles("admin","operator")
ADMIN=roles("admin")
LANGS=("fa","ar","en","ps","prs")
INTENTS=("greeting","appointment","quote","documents","visa","human","general")
KEY_PATTERN=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")
DIGEST_PATTERN=re.compile(r"^[a-f0-9]{64}$")

def demo_only():
    if os.getenv("APP_ENV","development") not in ("development","test"):
        raise HTTPException(503,"Real patient voice messaging is not approved")

def sample_response(row):
    return {"id":row.id,"kind":row.kind,"locale":row.locale,
        "status":row.status,"source_format":row.source_format,
        "duration_ms":row.duration_ms,
        "audio_sha256":row.audio_sha256,
        "transcript_sha256":row.transcript_sha256,
        "author_id":row.author_id,"reviewer_id":row.reviewer_id,
        "created_at":row.created_at,
        "raw_audio_stored":False,"raw_transcript_stored":False,
        "message_sent":False,"clinical_use_authorized":False}

@router.get("/readiness")
def voice_readiness(user:User=Depends(STAFF)):
    return {"supported_locales":list(LANGS),
        "input_codecs":["wav_pcm16_mono","ogg_opus_with_ffmpeg"],
        "max_input_bytes":MAX_INPUT_BYTES,"max_duration_seconds":30,
        "stt_enabled_locales":[l for l in LANGS if readiness("stt",l)],
        "tts_enabled_locales":[l for l in LANGS if readiness("tts",l)],
        "dari_dialect_validated_independently":False,
        "pashto_dialect_validated_independently":False,
        "demo_only":True,"channel_voice_ingestion_enabled":False,
        "medical_record_processing_enabled":False,
        "transcript_persisted":False,"audio_persisted":False,
        "outbound_automation_enabled":False}

@router.post("/transcribe",status_code=201)
async def transcription(
    response:Response,
    file:UploadFile=File(...),
    locale:Literal["fa","ar","en","ps","prs"]=Form(...),
    request_key:str=Form(...),
    synthetic_sample_only:bool=Form(...),
    db:Session=Depends(get_db),user:User=Depends(STAFF)):
    response.headers["Cache-Control"]="no-store, private"
    response.headers["X-Content-Type-Options"]="nosniff"
    demo_only()
    if not synthetic_sample_only:
        raise HTTPException(422,"Explicit synthetic-sample confirmation required")
    if not KEY_PATTERN.fullmatch(request_key):
        raise HTTPException(422,"Invalid idempotency key")
    if not readiness("stt",locale):
        raise HTTPException(503,"STT language/provider not approved")
    throttle("voice-stt:"+user.tenant_id+":"+user.id,limit=15,window=3600)
    try:
        raw=await file.read(MAX_INPUT_BYTES+1)
    finally:
        await file.close()
    payload,ms,source_format=decode_voice(raw)
    audio_hash=hashlib.sha256(raw).hexdigest()
    # Serialize all voice requests in the same tenant, including idempotency.
    db.scalar(select(Tenant.id).where(Tenant.id==user.tenant_id).with_for_update())
    previous=db.scalar(select(VoiceSampleJob).where(
        VoiceSampleJob.tenant_id==user.tenant_id,VoiceSampleJob.request_key==request_key))
    if previous:
        if previous.kind!="stt" or previous.locale!=locale or previous.audio_sha256!=audio_hash:
            raise HTTPException(409,"Voice idempotency key conflict")
        return {**sample_response(previous),"draft_text":None,
            "deduplicated":True,"replay_unavailable_reason":"No transcripts stored"}
    transcript=provider_transcribe(payload,locale)
    if not transcript or len(transcript)>1500:
        raise HTTPException(502,"Invalid provider transcript")
    transcript_hash=hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    row=VoiceSampleJob(tenant_id=user.tenant_id,request_key=request_key,
        kind="stt",locale=locale,source_format=source_format,
        audio_sha256=audio_hash,transcript_sha256=transcript_hash,
        duration_ms=ms,status="pending_human_review",author_id=user.id)
    db.add(row);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="synthetic_stt_draft_created",entity_type="VoiceSampleJob",entity_id=row.id))
    db.commit()
    # Only this one response includes the ephemeral text; it is never logged or stored.
    return {**sample_response(row),"draft_text":transcript,
        "deduplicated":False,"human_review_required":True,
        "independent_language_quality_validated":False}

class ReviewIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    decision:Literal["approve_internal","reject"]
    transcript_text:str=Field(min_length=1,max_length=1500)
    evidence_reference:str=Field(min_length=6,max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$")

@router.post("/drafts/{sample_id}/review")
def review_transcript(sample_id:str,body:ReviewIn,db:Session=Depends(get_db),
                      user:User=Depends(ADMIN)):
    demo_only()
    row=db.scalar(select(VoiceSampleJob).where(
        VoiceSampleJob.tenant_id==user.tenant_id,
        VoiceSampleJob.id==sample_id).with_for_update())
    if not row:raise HTTPException(404,"Voice draft not found")
    if row.kind!="stt" or row.status!="pending_human_review":
        raise HTTPException(409,"Voice draft is not awaiting human review")
    if row.author_id==user.id:
        raise HTTPException(409,"STT reviewer must differ from sample author")
    if hashlib.sha256(body.transcript_text.encode("utf-8")).hexdigest()!=row.transcript_sha256:
        raise HTTPException(409,"Transcript hash mismatch; use exact draft text")
    row.status="approved_internal_only" if body.decision=="approve_internal" else "rejected"
    row.reviewer_id=user.id;row.review_reference=body.evidence_reference
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="synthetic_stt_human_reviewed",entity_type="VoiceSampleJob",entity_id=row.id))
    db.commit()
    return {**sample_response(row),"sent":False,"clinical_data_shared":False}

@router.get("/drafts")
def list_samples(db:Session=Depends(get_db),user:User=Depends(STAFF)):
    rows=db.scalars(select(VoiceSampleJob).where(
        VoiceSampleJob.tenant_id==user.tenant_id).order_by(
            VoiceSampleJob.created_at.desc()).limit(60)).all()
    return {"items":[sample_response(row) for row in rows]}

class SpeakIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    locale:Literal["fa","ar","en","ps","prs"]
    intent:Literal["greeting","appointment","quote","documents","visa","human","general"]
    synthetic_sample_only:Literal[True]

@router.post("/speak")
def speak(body:SpeakIn,db:Session=Depends(get_db),user:User=Depends(STAFF)):
    demo_only()
    if not readiness("tts",body.locale):
        raise HTTPException(503,"TTS language/provider not approved")
    throttle("voice-tts:"+user.tenant_id+":"+user.id,limit=15,window=3600)
    # No arbitrary speech input or voice-cloning. Approved static templates only.
    static_text=RESPONSES[body.locale][body.intent]
    raw,ms=provider_synthesize(static_text,body.locale)
    if not isinstance(raw,bytes) or not raw or len(raw)>1_100_000:
        raise HTTPException(502,"Invalid generated audio")
    digest=hashlib.sha256(raw).hexdigest()
    row=VoiceSampleJob(tenant_id=user.tenant_id,
        request_key="tts-"+__import__("uuid").uuid4().hex,
        kind="tts",locale=body.locale,source_format="wav",
        audio_sha256=digest,transcript_sha256=hashlib.sha256(static_text.encode()).hexdigest(),
        duration_ms=ms,status="preview_only",author_id=user.id)
    db.add(row);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
        event="synthetic_tts_preview_created",entity_type="VoiceSampleJob",entity_id=row.id))
    db.commit()
    return Response(content=raw,media_type="audio/wav",
        headers={"Cache-Control":"no-store, private",
                 "X-Content-Type-Options":"nosniff",
                 "X-Voice-Preview-Only":"true",
                 "X-Voice-Sample-Id":row.id})
