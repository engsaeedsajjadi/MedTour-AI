"""Optional, allowlisted OpenAI-compatible STT/TTS adapter.

The adapter NEVER uses patient content, credentials or provider destinations
supplied by requests. All production/real-PHI processing remains prohibited.
"""
from __future__ import annotations
import os
import httpx
from fastapi import HTTPException
from .ai import approved_provider_base_url
from .voice_processing import validate_wav

LOCALES={"fa","ar","en","ps","prs"}
STT_HINTS={"fa":"fa","ar":"ar","en":"en","ps":"ps","prs":"fa"}
MAX_TEXT=1500

def readiness(kind:str,locale:str)->bool:
    if kind not in ("stt","tts") or locale not in LOCALES:return False
    return all((
        os.getenv("APP_ENV","development") in ("development","test"),
        os.getenv("AI_PROVIDER_APPROVED","").lower()=="true",
        os.getenv("VOICE_PROCESSOR_APPROVED","").lower()=="true",
        os.getenv(f"VOICE_{kind.upper()}_ENABLED","").lower()=="true",
        os.getenv("AI_API_KEY",""),
        os.getenv(f"VOICE_{kind.upper()}_MODEL",""),
        approved_provider_base_url(),
        locale in {x.strip() for x in os.getenv(
            f"VOICE_VERIFIED_{kind.upper()}_LOCALES","").split(",")},
    ))

def require_ready(kind:str,locale:str)->str:
    if not readiness(kind,locale):
        raise HTTPException(503,"Voice processor and locale have not been approved for synthetic testing")
    root=approved_provider_base_url()
    if not root:raise HTTPException(503,"Approved voice provider endpoint unavailable")
    return root

def transcribe(wav_bytes:bytes,locale:str)->str:
    root=require_ready("stt",locale)
    try:
        with httpx.Client(timeout=24,follow_redirects=False) as client:
            r=client.post(root+"/audio/transcriptions",headers={
                "Authorization":"Bearer "+os.environ["AI_API_KEY"]},
                data={"model":os.environ["VOICE_STT_MODEL"],"language":STT_HINTS[locale]},
                files={"file":("synthetic.wav",wav_bytes,"audio/wav")})
            r.raise_for_status()
            text=r.json()["text"]
        if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT:
            raise ValueError("Invalid STT response")
        return text.strip()
    except (httpx.HTTPError,KeyError,ValueError,TypeError,IndexError) as exc:
        raise HTTPException(502,"Approved transcription provider failed") from exc

def synthesize(text:str,locale:str)->tuple[bytes,int]:
    root=require_ready("tts",locale)
    if not isinstance(text,str) or not text or len(text)>MAX_TEXT:
        raise HTTPException(422,"Unsafe TTS template")
    try:
        with httpx.Client(timeout=25,follow_redirects=False) as client:
            r=client.post(root+"/audio/speech",headers={
                "Authorization":"Bearer "+os.environ["AI_API_KEY"]},
                json={"model":os.environ["VOICE_TTS_MODEL"],"voice":"alloy",
                      "input":text,"response_format":"wav"})
            r.raise_for_status()
            raw=r.content
        if len(raw)>1_100_000:
            raise ValueError("Oversized TTS output")
        wav,ms=validate_wav(raw)
        return wav,ms
    except (httpx.HTTPError,ValueError,TypeError) as exc:
        raise HTTPException(502,"Approved speech synthesis provider failed") from exc
