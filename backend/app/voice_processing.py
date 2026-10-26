"""Bounded audio decoding for synthetic voice samples.

This is not a medical audio ingestion gateway. Never store uploaded bytes.
Unrecognized formats, decoder errors, silence, oversized/long audio fail closed.
"""
from __future__ import annotations
from io import BytesIO
import shutil,subprocess,wave
from fastapi import HTTPException

MAX_INPUT_BYTES=1_000_000
MAX_OUTPUT_BYTES=1_100_000
MAX_SECONDS=30
SUPPORTED_RATES={8000,16000,24000,48000}

def validate_wav(data:bytes)->tuple[bytes,int]:
    if len(data)>MAX_OUTPUT_BYTES:
        raise HTTPException(413,"Voice sample exceeds decoded size limit")
    if not data.startswith(b"RIFF") or data[8:12]!=b"WAVE":
        raise HTTPException(415,"Expected PCM WAV with RIFF header")
    try:
        with wave.open(BytesIO(data),"rb") as f:
            if f.getcomptype()!="NONE" or f.getnchannels()!=1 or f.getsampwidth()!=2:
                raise ValueError("Only mono 16-bit PCM supported")
            rate=f.getframerate()
            if rate not in SUPPORTED_RATES:raise ValueError("Unsupported WAV sample rate")
            frames=f.getnframes()
            if frames<=0 or frames>rate*MAX_SECONDS:
                raise HTTPException(422,"Audio duration must be 0-30 seconds")
            if len(f.readframes(frames))!=frames*2:
                raise ValueError("Truncated WAV PCM samples")
            return data,(frames*1000)//rate
    except HTTPException:
        raise
    except (ValueError,wave.Error,EOFError,OverflowError) as exc:
        raise HTTPException(415,"Invalid or unsupported PCM WAV") from exc

def convert_opus(raw:bytes)->bytes:
    if not shutil.which("ffmpeg"):
        raise HTTPException(503,"OGG/Opus decoder unavailable on this server")
    try:
        result=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
            "-f","ogg","-i","pipe:0","-vn","-sn","-dn","-t","31",
            "-ar","16000","-ac","1","-f","s16le","pipe:1"],
            input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=9,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise HTTPException(503,"Audio decoder failed or timed out")
    if result.returncode!=0:
        raise HTTPException(415,"Invalid OGG/Opus voice sample")
    pcm=result.stdout
    if len(pcm)==0 or len(pcm)%2 or len(pcm)>16000*MAX_SECONDS*2:
        raise HTTPException(422,"Invalid or overlong decoded audio")
    out=BytesIO()
    with wave.open(out,"wb") as writer:
        writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(16000)
        writer.writeframes(pcm)
    return out.getvalue()

def decode_voice(raw:bytes,claimed_type:str|None=None)->tuple[bytes,int,str]:
    if not raw:raise HTTPException(422,"Empty audio file")
    if len(raw)>MAX_INPUT_BYTES:
        raise HTTPException(413,"Audio input exceeds 1 MB")
    # Trust content signature, never the submitted MIME or filename.
    if raw.startswith(b"RIFF") and raw[8:12]==b"WAVE":
        payload,ms=validate_wav(raw)
        return payload,ms,"wav"
    if raw.startswith(b"OggS") and b"OpusHead" in raw[:512]:
        payload,ms=validate_wav(convert_opus(raw))
        return payload,ms,"ogg_opus"
    raise HTTPException(415,"Only PCM WAV and OGG/Opus samples are accepted")
