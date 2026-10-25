"""Synthetic, locally isolated tests of security, multilingual intake and messaging."""
import base64,os,uuid
import pytest
from fastapi import HTTPException
from app.intake import INTAKE_QUESTIONS,LANGUAGES,next_question
from app.secure_media import validate_file,scan_clamav,object_key,s3_ready
from app.rate_limit import throttle,_hits


def grant(client,headers,patient_id,purpose):
    result=client.post('/api/v1/consents',headers=headers,json={
        'patient_id':patient_id,'purpose':purpose,'accepted':True,'notice_version':'v2'})
    assert result.status_code==201,result.text


def _exchange_portal(client,invitation):
    body=invitation.json() if hasattr(invitation,"json") else invitation
    r=client.post("/api/v1/portal/session/exchange",json={
        "invitation_token":body["token"],"verification_code":body["demo_verification_code"]})
    assert r.status_code==201,r.text
    return r.json()["access_token"]


def portal(client,headers,patient_id):
    grant(client,headers,patient_id,'communication')
    result=client.post(f'/api/v1/portal/invites/{patient_id}',headers=headers)
    assert result.status_code==201,result.text
    return {'X-Patient-Access':_exchange_portal(client,result)}


def test_five_language_questions_are_distinct_and_complete():
    assert set(INTAKE_QUESTIONS)==set(LANGUAGES)
    for lang in LANGUAGES:
        assert len(INTAKE_QUESTIONS[lang])==5
        assert next_question(lang,0)
        assert next_question(lang,5) is None
        assert all(len(q)>8 for q in INTAKE_QUESTIONS[lang])


def test_patient_portal_can_complete_structured_intake(seeded):
    (client,auth,_,_),admin,p,case=seeded
    token=portal(client,admin,p['id'])
    start=client.post('/api/v1/portal/intake/sessions',headers=token,json={'case_id':case['id'],'language':'ps'})
    assert start.status_code==201,start.text
    session=start.json();assert session['next_prompt']==INTAKE_QUESTIONS['ps'][0]
    restarted=client.post('/api/v1/portal/intake/sessions',headers=token,json={'case_id':case['id'],'language':'ps'})
    assert restarted.json()['id']==session['id']
    for stage in range(5):
        res=client.post(f"/api/v1/portal/intake/sessions/{session['id']}/answer",headers=token,json={'answer':'Administrative answer '+str(stage)})
        assert res.status_code==200,res.text
        if stage<4:assert res.json()['next_prompt']==INTAKE_QUESTIONS['ps'][stage+1]
        else: assert res.json()['status']=='awaiting_clinician_review'
    assert client.post(f"/api/v1/portal/intake/sessions/{session['id']}/answer",headers=token,json={'answer':'duplicate'}).status_code==409
    assert client.post('/api/v1/portal/intake/sessions',headers=token,json={'case_id':case['id']}).status_code==409


def test_portal_intake_blocks_cross_patient_and_emergency(seeded):
    (client,auth,_,_),admin,p,c=seeded
    own=portal(client,admin,p['id'])
    second=client.post('/api/v1/patients',headers=admin,json={'full_name':'Other Synthetic Patient','language':'ar'}).json()
    grant(client,admin,second['id'],'intake')
    other=portal(client,admin,second['id'])
    assert client.post('/api/v1/portal/intake/sessions',headers=other,json={'case_id':c['id']}).status_code==404
    started=client.post('/api/v1/portal/intake/sessions',headers=own,json={'case_id':c['id'],'language':'en'}).json()
    emerg=client.post(f"/api/v1/portal/intake/sessions/{started['id']}/answer",headers=own,json={'answer':'I have chest pain'})
    assert emerg.status_code==200
    assert emerg.json()['status']=='requires_urgent_human_review'
    assert emerg.json()['emergency_keyword_detected'] is True
    assert client.get(f"/api/v1/portal/intake/sessions/{started['id']}",headers=other).status_code==404


def test_withdrawal_revokes_patient_portal_and_queued_templates(seeded):
    (client,auth,_,_),admin,p,c=seeded
    token=portal(client,admin,p['id'])
    assert client.get('/api/v1/portal/me',headers=token).status_code==200
    conv=client.post('/api/v1/conversations',headers=admin,json={'patient_id':p['id']}).json()
    from app.models import Conversation
    (_,_,_,Session),_,_,_=seeded
    with Session() as db:
        row=db.get(Conversation,conv['id']);row.channel='whatsapp';db.commit()
    payload={'conversation_id':conv['id'],'template_name':'please_check_secure_portal','locale':'en','idempotency_key':'the-request-key-001'}
    queued=client.post('/api/v1/communications/outbound',headers=admin,json=payload)
    assert queued.status_code==201,queued.text
    approved=client.post(f"/api/v1/communications/outbound/{queued.json()['id']}/approve",headers=admin)
    assert approved.status_code==200
    withdrawn=client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'communication','accepted':False,'notice_version':'v3'})
    assert withdrawn.status_code==201
    assert client.get('/api/v1/portal/me',headers=token).status_code==401
    outgoing=client.get('/api/v1/communications/outbound',headers=admin).json()
    assert outgoing[0]['status']=='blocked'


def test_outbound_is_deduplicated_and_never_auto_sent(seeded):
    (client,auth,_,_),admin,p,c=seeded
    grant(client,admin,p['id'],'communication')
    conv=client.post('/api/v1/conversations',headers=admin,json={'patient_id':p['id']}).json()
    from app.models import Conversation
    with seeded[0][3]() as db:
        row=db.get(Conversation,conv['id']);row.channel='whatsapp';db.commit()
    body={'conversation_id':conv['id'],'template_name':'case_update_available','locale':'ar','idempotency_key':'test-patient-queue-one'}
    first=client.post('/api/v1/communications/outbound',headers=admin,json=body)
    assert first.status_code==201
    second=client.post('/api/v1/communications/outbound',headers=admin,json=body)
    assert second.status_code==201 and second.json()['deduplicated']
    assert client.post('/api/v1/communications/outbound',headers=admin,json=body|{'template_name':'appointment_update_available'}).status_code==409
    assert client.post(f"/api/v1/communications/outbound/{first.json()['id']}/approve",headers=auth('a','operator@example.test')).status_code==403
    assert client.post(f"/api/v1/communications/outbound/{first.json()['id']}/approve",headers=admin).json()['sent'] is False
    from app.delivery import send_one
    assert send_one(first.json()['id'])['status']=='blocked'
    assert client.post('/api/v1/conversations/'+conv['id']+'/messages',headers=admin,json={'body':'No free form WhatsApp','language':'ar'}).status_code==409


def test_translation_consent_required_and_human_review(monkeypatch,seeded):
    (client,auth,_,_),admin,p,c=seeded
    conv=client.post('/api/v1/conversations',headers=admin,json={'patient_id':p['id']}).json()
    obj={'conversation_id':conv['id'],'source_language':'fa','target_language':'ps','source_text':'آماده بررسی'}
    assert client.post('/api/v1/communications/translation-drafts',headers=admin,json=obj).status_code==409
    grant(client,admin,p['id'],'communication')
    assert client.post('/api/v1/communications/translation-drafts',headers=admin,json=obj).status_code==409
    grant(client,admin,p['id'],'ai_processing')
    assert client.post('/api/v1/communications/translation-drafts',headers=admin,json=obj).status_code==503
    monkeypatch.setattr('app.communications.translate',lambda *args:'Initial machine translated DRAFT')
    r=client.post('/api/v1/communications/translation-drafts',headers=admin,json=obj)
    assert r.status_code==201,r.text
    assert 'DRAFT' in r.json()['draft_text']
    review=client.post('/api/v1/communications/translation-drafts/'+r.json()['id']+'/review',headers=admin,
       json={'action':'approve','approved_text':'Human reviewed localized copy'})
    assert review.status_code==200 and review.json()['delivered_to_webchat']
    assert client.post('/api/v1/communications/translation-drafts/'+r.json()['id']+'/review',headers=admin,
       json={'action':'approve','approved_text':'duplicate'}).status_code==409
    messages=client.get('/api/v1/conversations/'+conv['id']+'/messages',headers=admin).json()
    assert messages[0]['body']=='Human reviewed localized copy'


def test_patient_upload_private_dev_storage(monkeypatch,tmp_path,seeded):
    (client,auth,_,_),admin,p,c=seeded
    headers=portal(client,admin,p['id'])
    grant(client,admin,p['id'],'medical_documents')
    monkeypatch.setenv('ALLOW_DEV_ENCRYPTED_UPLOADS','true')
    monkeypatch.setenv('DOCUMENT_ENCRYPTION_KEY',base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv('PRIVATE_DOCUMENT_DIR',str(tmp_path))
    file={'file':('sample.pdf',b'%PDF-1.4\nexample test data', 'application/pdf')}
    res=client.post('/api/v1/secure-documents/portal/cases/'+c['id'],headers=headers,files=file)
    assert res.status_code==201,res.text
    assert res.json()['status']=='encrypted_dev_unscanned'
    assert client.get('/api/v1/secure-documents/portal/cases/'+c['id']+'/list',headers=headers).json()[0]['id']==res.json()['id']
    assert client.get('/api/v1/secure-documents/'+res.json()['id'],headers=admin).status_code==200
    other=client.post('/api/v1/patients',headers=admin,json={'full_name':'Another Fake Patient','language':'en'}).json()
    grant(client,admin,other['id'],'communication')
    grant(client,admin,other['id'],'intake')
    other_header=client.post('/api/v1/portal/invites/'+other['id'],headers=admin).json()
    assert client.get('/api/v1/secure-documents/portal/cases/'+c['id']+'/list',headers={'X-Patient-Access':_exchange_portal(client,other_header)}).status_code==404
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'medical_documents','accepted':False,'notice_version':'v3'})
    assert client.get('/api/v1/secure-documents/'+res.json()['id'],headers=admin).status_code==409
    assert client.get('/api/v1/secure-documents/portal/cases/'+c['id']+'/list',headers=headers).status_code==401


def test_storage_and_scanner_fail_closed(monkeypatch):
    assert validate_file(b'%PDF-1.4\nSynthetic')[0]=='application/pdf'
    with pytest.raises(HTTPException) as x:validate_file(b'<html>malicious</html>')
    assert x.value.status_code==415
    monkeypatch.delenv('CLAMAV_HOST',raising=False)
    with pytest.raises(HTTPException) as x:scan_clamav(b'%PDF-1.4')
    assert x.value.status_code==503
    assert not s3_ready()
    t=str(uuid.uuid4());d=str(uuid.uuid4())
    assert t in object_key(t,d)
    with pytest.raises(ValueError):object_key('../',d)


def test_rate_limit_denies_repeated_attempts():
    _hits.clear()
    for _ in range(3):throttle('test'+str(uuid.uuid4()),limit=1)
    throttle('rate-limited-target',limit=2)
    throttle('rate-limited-target',limit=2)
    with pytest.raises(HTTPException) as exc:throttle('rate-limited-target',limit=2)
    assert exc.value.status_code==429
    _hits.clear()


def test_consent_link_patient_attestation_one_time(seeded):
    (client,auth,_,_),admin,p,c=seeded
    issued=client.post(f"/api/v1/consent-links/{p['id']}/medical_documents",headers=admin)
    assert issued.status_code==201
    raw=issued.json()['token']
    result=client.post('/api/v1/consent-links/respond',json={'token':raw,'notice_version':'v7','accepted':True})
    assert result.status_code==201,result.text
    assert result.json()['source']=='patient_link'
    assert client.post('/api/v1/consent-links/respond',json={'token':raw,'notice_version':'v7','accepted':True}).status_code==401
    grant(client,admin,p['id'],'communication')
    invite=client.post(f'/api/v1/portal/invites/{p["id"]}',headers=admin)
    assert invite.status_code==201
    access=_exchange_portal(client,invite)
    refused=client.post(f"/api/v1/consent-links/{p['id']}/communication",headers=admin).json()
    withdrawn=client.post('/api/v1/consent-links/respond',json={'token':refused['token'],'notice_version':'v8','accepted':False})
    assert withdrawn.status_code==201
    assert client.get('/api/v1/portal/me',headers={'X-Patient-Access':access}).status_code==401


def test_consent_link_cannot_be_used_for_other_purpose(seeded):
    (client,auth,_,_),admin,p,c=seeded
    assert client.post(f"/api/v1/consent-links/{p['id']}/marketing",headers=admin).status_code==422
    response=client.post('/api/v1/consent-links/respond',json={'token':'x'*50,'notice_version':'v1','accepted':True})
    assert response.status_code==401


def test_s3_kms_encryption_config_and_integrity_with_fake_storage(monkeypatch):
    """No AWS network calls: verify exact SSE-KMS request and checksum guard."""
    import hashlib
    from io import BytesIO
    from app import secure_media
    content=b'%PDF-1.4\nSynthetic Data\n'
    saved={}
    class FakeS3:
        def put_object(self,**kwargs):
            saved.update(kwargs)
        def get_object(self,**kwargs):
            assert kwargs['Bucket']=='fake-private-medical'
            assert kwargs['Key']==saved['Key']
            return {'Body':BytesIO(saved['Body'])}
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('DOCUMENT_PROCESSING_APPROVED','true')
    monkeypatch.setenv('MEDICAL_S3_BUCKET','fake-private-medical')
    monkeypatch.setenv('MEDICAL_S3_KMS_KEY_ID','arn:aws:kms:fake')
    monkeypatch.setenv('CLAMAV_HOST','scanner.internal')
    monkeypatch.setattr(secure_media,'s3_client',lambda:FakeS3())
    tenant=str(uuid.uuid4());doc=str(uuid.uuid4());mime,checksum=validate_file(content)
    key=secure_media.s3_store(tenant,doc,content,mime)
    assert saved['ServerSideEncryption']=='aws:kms'
    assert saved['SSEKMSKeyId']=='arn:aws:kms:fake'
    assert saved['Metadata']['integrity-sha256']==checksum
    assert secure_media.s3_load(key,tenant,doc,checksum)==content
    saved['Body']=content+b'tampered'
    with pytest.raises(HTTPException) as exc:secure_media.s3_load(key,tenant,doc,checksum)
    assert exc.value.status_code==500


def test_staff_document_ticket_returns_real_authenticated_routes_only(seeded,monkeypatch,tmp_path):
    (client,auth,_,_),admin,p,c=seeded
    grant(client,admin,p['id'],'medical_documents')
    payload={'patient_id':p['id'],'case_id':c['id'],'filename':'safe.pdf','category':'report'}
    assert client.post('/api/v1/documents/upload-ticket',headers=admin,json=payload).status_code==503
    monkeypatch.setenv('ALLOW_DEV_ENCRYPTED_UPLOADS','true')
    monkeypatch.setenv('DOCUMENT_ENCRYPTION_KEY',base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv('PRIVATE_DOCUMENT_DIR',str(tmp_path))
    result=client.post('/api/v1/documents/upload-ticket',headers=admin,json=payload)
    assert result.status_code==200,result.text
    assert result.json()['presigned_public_url'] is None
    assert '/portal/cases/' in result.json()['patient_endpoint']
