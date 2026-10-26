"""Wire-level voice provider contract checks without external network."""
from io import BytesIO
import wave
from fastapi import HTTPException
import pytest
from app import voice_provider

def silent_wav():
    out=BytesIO()
    with wave.open(out,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        w.writeframes(b"\x00\x00"*3200)
    return out.getvalue()

def configure(monkeypatch):
    for name,value in {
        "APP_ENV":"test","AI_PROVIDER_APPROVED":"true",
        "VOICE_PROCESSOR_APPROVED":"true",
        "VOICE_STT_ENABLED":"true","VOICE_TTS_ENABLED":"true",
        "AI_API_KEY":"FAKE-ONLY-TEST",
        "AI_BASE_URL":"https://synthetic-voice.example",
        "AI_APPROVED_HOSTS":"synthetic-voice.example",
        "VOICE_STT_MODEL":"test-whisper",
        "VOICE_TTS_MODEL":"test-speech",
        "VOICE_VERIFIED_STT_LOCALES":"fa,ar,en,ps,prs",
        "VOICE_VERIFIED_TTS_LOCALES":"fa,ar,en,ps,prs",
    }.items():monkeypatch.setenv(name,value)

def test_stt_provider_multipart_and_dari_language_hint(monkeypatch):
    configure(monkeypatch)
    captured=[]
    class FakeResponse:
        def raise_for_status(self):pass
        def json(self):return {"text":"Synthetic test sample"}
    class FakeClient:
        def __init__(self,**kwargs):assert kwargs["follow_redirects"] is False
        def __enter__(self):return self
        def __exit__(self,*args):return None
        def post(self,url,**kwargs):
            captured.append((url,kwargs))
            return FakeResponse()
    monkeypatch.setattr(voice_provider.httpx,"Client",FakeClient)
    assert voice_provider.transcribe(silent_wav(),"prs")=="Synthetic test sample"
    assert captured[0][0]=="https://synthetic-voice.example/audio/transcriptions"
    assert captured[0][1]["data"]=={"model":"test-whisper","language":"fa"}
    assert captured[0][1]["files"]["file"][2]=="audio/wav"
    assert captured[0][1]["headers"]["Authorization"]=="Bearer FAKE-ONLY-TEST"

def test_tts_provider_static_wav_contract_and_untrusted_response_fails(monkeypatch):
    configure(monkeypatch)
    seen=[]
    class Response:
        def __init__(self,audio):self.content=audio
        def raise_for_status(self):pass
    class FakeClient:
        def __init__(self,**kwargs):assert kwargs["follow_redirects"] is False
        def __enter__(self):return self
        def __exit__(self,*args):return None
        def post(self,url,**kwargs):
            seen.append((url,kwargs))
            return Response(silent_wav() if len(seen)==1 else b"<html>not audio</html>")
    monkeypatch.setattr(voice_provider.httpx,"Client",FakeClient)
    payload,ms=voice_provider.synthesize("Generic admin greeting","ps")
    assert payload.startswith(b"RIFF") and ms==100
    assert seen[0][0]=="https://synthetic-voice.example/audio/speech"
    assert seen[0][1]["json"]["voice"]=="alloy"
    assert seen[0][1]["json"]["response_format"]=="wav"
    with pytest.raises(HTTPException) as error:
        voice_provider.synthesize("Another generic greeting","fa")
    assert error.value.status_code==415

def test_misconfigured_voice_provider_fails_without_network(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("VOICE_VERIFIED_STT_LOCALES","en")
    with pytest.raises(HTTPException) as e:
        voice_provider.transcribe(silent_wav(),"ps")
    assert e.value.status_code==503
    monkeypatch.setenv("VOICE_VERIFIED_TTS_LOCALES","")
    with pytest.raises(HTTPException) as e:
        voice_provider.synthesize("Safe text","ar")
    assert e.value.status_code==503
