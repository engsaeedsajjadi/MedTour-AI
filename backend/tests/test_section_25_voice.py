"""Synthetic-only multilingual voice media security and reviewed STT/TTS tests."""
from io import BytesIO
import hashlib,wave
from app.enterprise_models import VoiceSampleJob
from app.voice_processing import decode_voice,validate_wav
from fastapi import HTTPException
import pytest

BASE="/api/v1/voice"

def wav(rate=16000,seconds=1):
    out=BytesIO()
    with wave.open(out,"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate)
        f.writeframes(b"\x00\x00"*rate*seconds)
    return out.getvalue()

def setup_stt(monkeypatch):
    import app.voice_api as api
    monkeypatch.setattr(api,"readiness",lambda kind,locale:kind in ("stt","tts"))
    calls=[]
    def transcribe(payload,locale):
        calls.append((len(payload),locale))
        return {"fa":"متن آزمایشی غیر درمانی","ar":"نص تجريبي إداري",
                "en":"Synthetic administrative request",
                "ps":"ازمايښتي اداري غږ","prs":"متن اداری آزمایشی"}[locale]
    monkeypatch.setattr(api,"provider_transcribe",transcribe)
    monkeypatch.setattr(api,"provider_synthesize",lambda text,locale:(wav(),1000))
    return calls

def upload(client,auth,locale="fa",key="VOICE-REQUEST-100",payload=None,flag="true",
           filename="synthetic.wav",content_type="audio/wav"):
    return client.post(BASE+"/transcribe",headers=auth,
        data={"locale":locale,"request_key":key,"synthetic_sample_only":flag},
        files={"file":(filename,payload if payload is not None else wav(),content_type)})

def test_provider_readiness_fail_closed_by_default(context,monkeypatch):
    import app.voice_provider as provider
    client,auth,_,_=context
    admin=auth("a")
    data=client.get(BASE+"/readiness",headers=admin)
    assert data.status_code==200,data.text
    j=data.json()
    assert j["supported_locales"]==["fa","ar","en","ps","prs"]
    assert j["channel_voice_ingestion_enabled"] is False
    assert j["audio_persisted"] is False
    assert j["stt_enabled_locales"]==[]
    assert j["tts_enabled_locales"]==[]
    assert upload(client,admin).status_code==503
    assert client.post(BASE+"/speak",headers=admin,json={
        "locale":"ar","intent":"greeting","synthetic_sample_only":True}).status_code==503
    monkeypatch.setenv("AI_PROVIDER_APPROVED","true")
    monkeypatch.setenv("VOICE_PROCESSOR_APPROVED","true")
    monkeypatch.setenv("VOICE_STT_ENABLED","true")
    monkeypatch.setenv("VOICE_STT_MODEL","synthetic-stt")
    monkeypatch.setenv("VOICE_VERIFIED_STT_LOCALES","fa,ar,en,ps,prs")
    monkeypatch.setenv("AI_API_KEY","synthetic-not-real-key")
    monkeypatch.setenv("AI_BASE_URL","http://unsafe.example")
    monkeypatch.setenv("AI_APPROVED_HOSTS","unsafe.example")
    assert provider.readiness("stt","fa") is False
    monkeypatch.setenv("AI_BASE_URL","https://approved.example")
    monkeypatch.setenv("AI_APPROVED_HOSTS","approved.example")
    assert provider.readiness("stt","ps") is True
    assert provider.readiness("tts","fa") is False
    assert provider.readiness("stt","xx") is False
    monkeypatch.setenv("APP_ENV","staging")
    assert provider.readiness("stt","fa") is False

def test_stt_five_languages_never_stores_audio_or_text(context,monkeypatch):
    client,auth,_,Session=context
    calls=setup_stt(monkeypatch)
    admin=auth("a")
    for i,loc in enumerate(["fa","ar","en","ps","prs"]):
        res=upload(client,admin,locale=loc,key=f"VOICE-SAMPLE-{i:03}")
        assert res.status_code==201,res.text
        j=res.json()
        assert j["locale"]==loc
        assert j["draft_text"] and j["status"]=="pending_human_review"
        assert j["source_format"]=="wav"
        assert j["duration_ms"]==1000
        assert j["raw_audio_stored"] is False
        assert j["raw_transcript_stored"] is False
        assert j["message_sent"] is False
        assert len(j["transcript_sha256"])==64
        assert j["transcript_sha256"]==hashlib.sha256(j["draft_text"].encode()).hexdigest()
        listing=client.get(BASE+"/drafts",headers=admin).json()["items"]
        assert "draft_text" not in str(listing)
        with Session() as db:
            row=db.query(VoiceSampleJob).filter(VoiceSampleJob.id==j["id"]).one()
            assert not hasattr(row,"raw_audio") and not hasattr(row,"draft_text")
            assert len(row.audio_sha256)==64
            assert row.transcript_sha256==j["transcript_sha256"]
    assert len(calls)==5
    response=client.get(BASE+"/drafts",headers=admin)
    assert response.headers["content-type"].startswith("application/json")

def test_stt_idempotency_and_tenant_boundaries(context,monkeypatch):
    client,auth,_,Session=context
    calls=setup_stt(monkeypatch)
    staff=auth("a","operator@example.test")
    other=auth("b")
    created=upload(client,staff,locale="en",key="SAMPLE-IDEMPOTENCY-1")
    assert created.status_code==201
    sample_id=created.json()["id"]
    repeat=upload(client,staff,locale="en",key="SAMPLE-IDEMPOTENCY-1")
    assert repeat.status_code==201
    assert repeat.json()["deduplicated"] is True
    assert repeat.json()["draft_text"] is None
    assert len(calls)==1
    assert upload(client,staff,locale="fa",key="SAMPLE-IDEMPOTENCY-1").status_code==409
    assert client.get(BASE+"/drafts",headers=other).json()["items"]==[]
    assert client.post(BASE+"/drafts/"+sample_id+"/review",headers=other,json={
        "decision":"reject","transcript_text":"Synthetic administrative request",
        "evidence_reference":"SYNTH-REVIEW-0001"}).status_code==404
    assert upload(client,other,locale="en",key="SAMPLE-IDEMPOTENCY-1").status_code==201
    assert len(calls)==2

def test_stt_review_rejects_self_and_changed_transcripts(context,monkeypatch):
    client,auth,_,Session=context
    setup_stt(monkeypatch)
    admin=auth("a")
    operator=auth("a","operator@example.test")
    sample=upload(client,operator,locale="en")
    assert sample.status_code==201
    j=sample.json()
    payload={"decision":"approve_internal","transcript_text":j["draft_text"],
        "evidence_reference":"SYNTH-REVIEW-ABCDE"}
    assert client.post(BASE+"/drafts/"+j["id"]+"/review",headers=operator,json=payload).status_code==403
    assert client.post(BASE+"/drafts/"+j["id"]+"/review",headers=admin,
        json=payload|{"transcript_text":"Altered text"}).status_code==409
    approved=client.post(BASE+"/drafts/"+j["id"]+"/review",headers=admin,json=payload)
    assert approved.status_code==200,approved.text
    assert approved.json()["status"]=="approved_internal_only"
    assert approved.json()["sent"] is False
    assert client.post(BASE+"/drafts/"+j["id"]+"/review",headers=admin,json=payload).status_code==409
    own=upload(client,admin,key="VOICE-SELF-REVIEW-2")
    assert own.status_code==201
    assert client.post(BASE+"/drafts/"+own.json()["id"]+"/review",
        headers=admin,json=payload|{"transcript_text":own.json()["draft_text"]}).status_code==409

def test_wav_limits_and_content_sniffing(context,monkeypatch):
    client,auth,_,Session=context
    setup_stt(monkeypatch)
    admin=auth("a")
    assert upload(client,admin,flag="false").status_code==422
    assert upload(client,admin,payload=b"fake wav",filename="fake.wav").status_code==415
    assert upload(client,admin,payload=b"MZ"+b"x"*50,filename="synthetic.wav").status_code==415
    assert upload(client,admin,payload=b"OggS"+b"x"*50,
                  content_type="audio/ogg").status_code==415
    assert upload(client,admin,payload=b"x"*1_000_001).status_code==413
    assert upload(client,admin,payload=wav(seconds=31)).status_code==413
    assert upload(client,admin,payload=wav(rate=16000,seconds=0)).status_code==422
    assert upload(client,admin,payload=wav(rate=11025)).status_code==415
    assert upload(client,admin,payload=wav()[:-100]).status_code==415
    assert upload(client,admin,key="short").status_code==422
    assert upload(client,admin,filename="f.wav",content_type="text/plain").status_code==201

def test_opus_decoder_is_bounded_and_optional(monkeypatch):
    import app.voice_processing as audio
    fake=b"OggS"+b"\x00"*30+b"OpusHead"+b"synthetic"*10
    monkeypatch.setattr(audio,"convert_opus",lambda _:wav())
    payload,ms,kind=decode_voice(fake)
    assert payload.startswith(b"RIFF") and ms==1000 and kind=="ogg_opus"
    monkeypatch.setattr(audio.shutil,"which",lambda x:None)
    with pytest.raises(HTTPException) as err:
        audio.convert_opus(fake)
    assert err.value.status_code==503

def test_static_tts_only_and_no_persisted_binary(context,monkeypatch):
    import app.voice_api as api
    client,auth,_,Session=context
    setup_stt(monkeypatch)
    admin=auth("a")
    data={"locale":"ps","intent":"greeting","synthetic_sample_only":True}
    output=client.post(BASE+"/speak",headers=admin,json=data)
    assert output.status_code==200,output.text[:400] if output.status_code!=200 else ""
    assert output.content.startswith(b"RIFF")
    assert output.headers["content-type"].startswith("audio/wav")
    assert output.headers["cache-control"].startswith("no-store")
    assert output.headers["X-Voice-Preview-Only"]=="true"
    assert client.post(BASE+"/speak",headers=admin,json=data|{"text":"private patient note"}).status_code==422
    assert client.post(BASE+"/speak",headers=admin,json=data|{"synthetic_sample_only":False}).status_code==422
    with Session() as db:
        item=db.query(VoiceSampleJob).filter(VoiceSampleJob.kind=="tts").one()
        assert item.status=="preview_only" and item.transcript_sha256 is not None
        assert item.audio_sha256==hashlib.sha256(output.content).hexdigest()
    assert client.get(BASE+"/drafts",headers=admin).json()["items"][0]["kind"]=="tts"

def test_environment_denial_and_role_boundary(context,monkeypatch):
    client,auth,_,Session=context
    setup_stt(monkeypatch)
    admin=auth("a")
    assert client.get(BASE+"/readiness").status_code==401
    monkeypatch.setenv("APP_ENV","staging")
    assert upload(client,admin).status_code==503
    assert client.post(BASE+"/speak",headers=admin,json={
        "locale":"en","intent":"greeting","synthetic_sample_only":True}).status_code==503
    monkeypatch.setenv("APP_ENV","test")
    assert upload(client,admin).status_code==201
