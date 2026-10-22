"""Synthetic contract tests; no real clinical data or provider requests."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from io import BytesIO
import base64,os,hmac,hashlib,json

def test_operations_lifecycle_and_tenant_isolation(seeded):
    (client,auth,_,_),admin,p,c=seeded
    x=client.post('/api/v1/operations',headers=admin,json={'kind':'visa','case_id':c['id'],'title':'Travel documentation'});assert x.status_code==201,x.text
    item=x.json()
    other=auth('b')
    assert client.get('/api/v1/operations/'+item['id']+'/history',headers=other).status_code==404
    assert client.get('/api/v1/operations',headers=other).json()==[]
    assert client.post('/api/v1/operations/'+item['id']+'/transition',headers=admin,json={'status':'confirmed','reference':'gov-issued'}).status_code==409
    assert client.post('/api/v1/operations/'+item['id']+'/transition',headers=admin,json={'status':'in_review'}).status_code==200
    assert client.post('/api/v1/operations/'+item['id']+'/transition',headers=admin,json={'status':'awaiting_external'}).status_code==200
    assert client.post('/api/v1/operations/'+item['id']+'/transition',headers=admin,json={'status':'confirmed'}).status_code==422
    ok=client.post('/api/v1/operations/'+item['id']+'/transition',headers=admin,json={'status':'confirmed','reference':'verified-authority-123'})
    assert ok.status_code==200 and ok.json()['confirmed_reference']=='verified-authority-123'
    assert len(client.get('/api/v1/operations/'+item['id']+'/history',headers=admin).json())==3

def test_operation_cannot_link_foreign_patient(seeded):
    (client,auth,_,_),admin,p,c=seeded
    own=client.post('/api/v1/patients',headers=admin,json={'full_name':'Other Synthetic','language':'en'}).json()
    r=client.post('/api/v1/operations',headers=admin,json={'kind':'visa','case_id':c['id'],'patient_id':own['id'],'title':'Mismatched'})
    assert r.status_code==422

def test_content_publish_and_public_gate(context):
    client,auth,_,_=context;a=auth('a')
    inp={'slug':'medical-services','locale':'ar','title':'الخدمات الطبية','body':'Available services reviewed by specialists'}
    created=client.post('/api/v1/cms/pages',headers=a,json=inp);assert created.status_code==201
    link='/api/v1/public/a/pages/ar/medical-services'
    assert client.get(link).status_code==404
    assert client.patch('/api/v1/cms/pages/'+created.json()['id']+'/publish',headers=a).status_code==200
    assert client.get(link).json()['title']==inp['title']
    assert client.get('/api/v1/public/b/pages/ar/medical-services').status_code==404

def test_knowledge_requires_supervisor(context):
    client,auth,_,_=context;admin=auth('a');op=auth('a','operator@example.test')
    x=client.post('/api/v1/knowledge',headers=op,json={'locale':'ps','title':'Travel information','body':'General coordination and contact procedures'})
    assert x.status_code==201
    assert client.patch('/api/v1/knowledge/'+x.json()['id']+'/approve',headers=op).status_code==403
    assert client.patch('/api/v1/knowledge/'+x.json()['id']+'/approve',headers=admin).json()['approved'] is True

def test_agent_link_and_cannot_leak_across_tenants(seeded):
    (client,auth,_,_),admin,p,c=seeded
    a=client.post('/api/v1/agents',headers=admin,json={'name':'Synthetic Agency','country':'AF'}).json()
    assert len(a['referral_code'])>10
    assert client.get('/api/v1/agents',headers=auth('b')).json()==[]
    assert client.post('/api/v1/lead-sources',headers=admin,json={'patient_id':p['id'],'agent_id':a['id'],'source':'agent'}).status_code==201
    assert client.post('/api/v1/lead-sources',headers=auth('b'),json={'patient_id':p['id'],'source':'agent'}).status_code==404

def test_quote_items_and_approved_immutability(seeded):
    (client,auth,_,_),admin,p,c=seeded
    q=client.post('/api/v1/quotes',headers=admin,json={'case_id':c['id'],'currency':'USD','amount_minor':0}).json()
    path='/api/v1/quotes/'+q['id']+'/items'
    item={'label':'Review of files','units':2,'unit_amount_minor':3000,'provenance':'Verified manual provider quote ABC'}
    r=client.post(path,headers=admin,json=item);assert r.status_code==201 and r.json()['quote_total_minor']==6000
    assert len(client.get(path,headers=admin).json())==1
    assert client.patch('/api/v1/quotes/'+q['id']+'/approve',headers=admin).status_code==200
    assert client.post(path,headers=admin,json=item).status_code==409

def test_verified_manual_money_idempotency(seeded):
    (client,auth,_,_),admin,p,c=seeded
    payload={'case_id':c['id'],'entry_type':'payment_received','currency':'USD','amount_minor':2500,'source_reference':'synthetic-receipt-101'}
    x=client.post('/api/v1/finance/entries',headers=admin,json=payload);assert x.status_code==201,x.text
    assert client.post('/api/v1/finance/entries',headers=admin,json=payload).status_code==409
    assert client.get('/api/v1/finance/entries',headers=auth('b')).json()==[]

def test_portal_access_requires_consent_and_own_patient_data(seeded):
    (client,auth,_,_),admin,p,c=seeded
    assert client.post('/api/v1/portal/invites/'+p['id'],headers=admin).status_code==409
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'communication','accepted':True,'notice_version':'v1'})
    response=client.post('/api/v1/portal/invites/'+p['id'],headers=admin)
    assert response.status_code==201
    token=response.json()['token'];h={'X-Patient-Access':token}
    assert client.get('/api/v1/portal/me',headers=h).json()['id']==p['id']
    trip=client.get('/api/v1/portal/journey',headers=h).json()
    assert len(trip)==1 and trip[0]['case_id']==c['id']
    assert client.get('/api/v1/portal/me',headers={'X-Patient-Access':'wrong'}).status_code==401
    assert client.post('/api/v1/portal/invites/revoke/'+p['id'],headers=admin).json()['revoked']==1
    assert client.get('/api/v1/portal/me',headers=h).status_code==401

def test_structured_intake_and_emergency_handoff(seeded):
    (client,auth,_,_),admin,p,c=seeded
    x=client.post('/api/v1/intake/sessions',headers=admin,json={'case_id':c['id'],'language':'prs'});assert x.status_code==201
    s=x.json();assert s['stage']==0
    x=client.post('/api/v1/intake/sessions/'+s['id']+'/answer',headers=admin,json={'answer':'Consultation'});assert x.json()['stage']==1
    x=client.post('/api/v1/intake/sessions/'+s['id']+'/answer',headers=admin,json={'answer':'درد قفسه سینه'})
    assert x.status_code==200 and x.json()['emergency_keyword_detected'] is True
    assert client.post('/api/v1/intake/sessions/'+s['id']+'/answer',headers=admin,json={'answer':'Another'}).status_code==409

def test_settings_allowlist(context):
    client,auth,_,_=context;h=auth('a')
    assert client.put('/api/v1/settings/ai_secret',headers=h,json={'value':{'password':'bad'}}).status_code==422
    x=client.put('/api/v1/settings/brand',headers=h,json={'value':{'name':'Test service'}})
    assert x.status_code==200
    assert client.get('/api/v1/settings',headers=auth('b')).json()=={}

def test_encrypted_dev_documents_unavailable_by_default(seeded):
    (client,auth,_,_),admin,p,c=seeded
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'medical_documents','accepted':True,'notice_version':'v1'})
    r=client.post('/api/v1/secure-documents/cases/'+c['id'],headers=admin,files={'file':('report.pdf',b'%PDF-1.4\nsynthetic','application/pdf')})
    assert r.status_code==503

def test_encrypted_dev_documents_roundtrip_and_isolation(seeded,monkeypatch,tmp_path):
    (client,auth,_,_),admin,p,c=seeded
    import secrets
    monkeypatch.setenv('ALLOW_DEV_ENCRYPTED_UPLOADS','true');monkeypatch.setenv('PRIVATE_DOCUMENT_DIR',str(tmp_path))
    monkeypatch.setenv('DOCUMENT_ENCRYPTION_KEY',base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'medical_documents','accepted':True,'notice_version':'v1'})
    raw=b'%PDF-1.4\nSYNTHETIC TEST DOCUMENT'
    x=client.post('/api/v1/secure-documents/cases/'+c['id'],headers=admin,files={'file':('report.pdf',raw,'application/pdf')})
    assert x.status_code==201,x.text
    ident=x.json()['id']
    assert b'SYNTHETIC' not in next(tmp_path.rglob('*.enc')).read_bytes()
    assert client.get('/api/v1/secure-documents/'+ident,headers=admin).content==raw
    assert client.get('/api/v1/secure-documents/'+ident,headers=auth('b')).status_code==404
    monkeypatch.delenv('ALLOW_DEV_ENCRYPTED_UPLOADS')

def test_webhook_routed_only_with_consent_and_signature(seeded,monkeypatch):
    (client,auth,_,Session),admin,p,c=seeded
    from app.models import Tenant
    from sqlalchemy import select
    with Session() as db:tid=db.scalar(select(Tenant.slug).where(Tenant.id==c['id'])) if False else 'a'
    monkeypatch.setenv('WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED','true')
    monkeypatch.setenv('WHATSAPP_INBOUND_PROCESSING_APPROVED','true')
    monkeypatch.setenv('META_APP_SECRET','synthetic-app-secret')
    monkeypatch.setenv('META_VERIFY_TOKEN','synthetic-verify')
    monkeypatch.setenv('WHATSAPP_TENANT_SLUG','a')
    monkeypatch.setenv('WHATSAPP_PHONE_NUMBER_ID','number-001')
    payload={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{
       'metadata':{'phone_number_id':'number-001'},'messages':[{'id':'wamid.test-example-12345','from':'9990000000','type':'text','text':{'body':'synthetic greeting'}}]}}]}]}
    raw=json.dumps(payload).encode();sig='sha256='+hmac.new(b'synthetic-app-secret',raw,hashlib.sha256).hexdigest()
    r=client.post('/api/v1/webhooks/whatsapp',content=raw,headers={'X-Hub-Signature-256':sig,'Content-Type':'application/json'})
    assert r.status_code==200 and r.json()['quarantined']==1
    assert client.post('/api/v1/webhooks/whatsapp',content=raw,headers={'X-Hub-Signature-256':sig,'Content-Type':'application/json'}).json()['duplicates']==1
    assert client.get('/api/v1/conversations',headers=admin).json()==[]

def test_patient_chat_is_consent_gated_and_scoped(seeded):
    (client,auth,_,_),admin,p,c=seeded
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'communication','accepted':True,'notice_version':'v1'})
    token=client.post('/api/v1/portal/invites/'+p['id'],headers=admin).json()['token']
    h={'X-Patient-Access':token}
    resp=client.post('/api/v1/portal/chat',headers=h,json={'message':'I would like to see a specialist','language':'en'})
    assert resp.status_code==201 and resp.json()['automated_response']
    history=client.get('/api/v1/portal/chat',headers=h).json()
    assert len(history)==2 and history[0]['sender']=='patient'
    emergency=client.post('/api/v1/portal/chat',headers=h,json={'message':'I have chest pain','language':'en'})
    assert emergency.json()['human_handoff'] is True
    assert emergency.json()['warning']
    assert client.post('/api/v1/portal/chat',headers={'X-Patient-Access':'fake'},json={'message':'Hi'}).status_code==401

def test_matching_only_verified_specialty_and_tenant(seeded):
    (client,auth,_,_),admin,p,c=seeded
    r=client.post('/api/v1/provider-options',headers=admin,json={'case_id':c['id']})
    assert r.status_code==200 and r.json()['results']==[]
    doc=client.post('/api/v1/physicians',headers=admin,json={'full_name':'Test Verified Cardiologist','specialty':'cardiology','city':'Tehran'}).json()
    assert client.post('/api/v1/provider-options',headers=admin,json={'case_id':c['id']}).json()['results']==[]
    client.patch('/api/v1/physicians/'+doc['id']+'/verification',headers=admin,json={'status':'verified'})
    results=client.post('/api/v1/provider-options',headers=admin,json={'case_id':c['id']}).json()
    assert results['status']=='requires_human_clinical_review' and len(results['results'])==1
    assert client.post('/api/v1/provider-options',headers=auth('b'),json={'case_id':c['id']}).status_code==404

def test_translation_does_not_run_without_consent_or_approved_provider(seeded):
    (client,auth,_,_),admin,p,c=seeded
    body={'patient_id':p['id'],'source_language':'fa','target_language':'ps','text':'سلام'}
    assert client.post('/api/v1/ai/translate-draft',headers=admin,json=body).status_code==409
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'ai_processing','accepted':True,'notice_version':'v1'})
    assert client.post('/api/v1/ai/translate-draft',headers=admin,json=body).status_code==503

def test_webhook_consent_based_routing_to_existing_patient(seeded,monkeypatch):
    (client,auth,_,Session),admin,p,c=seeded
    from app.models import Patient
    from sqlalchemy import select
    with Session() as db:
        pa=db.scalar(select(Patient).where(Patient.id==p['id']))
        pa.contact='1234567890';db.commit()
    client.post('/api/v1/consents',headers=admin,json={'patient_id':p['id'],'purpose':'communication','accepted':True,'notice_version':'v1'})
    for k,v in {'WHATSAPP_BUSINESS_ELIGIBILITY_APPROVED':'true','WHATSAPP_INBOUND_PROCESSING_APPROVED':'true',
        'META_APP_SECRET':'test-app-secret','META_VERIFY_TOKEN':'test-verify-token',
        'WHATSAPP_TENANT_SLUG':'a','WHATSAPP_PHONE_NUMBER_ID':'test-phone-001'}.items():monkeypatch.setenv(k,v)
    from app.whatsapp import enabled
    assert enabled()
    payload={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{'metadata':{'phone_number_id':'test-phone-001'},
        'messages':[{'id':'wamid.consent.test','from':'1234567890','type':'text','text':{'body':'Hello care coordination'}}]}}]}]}
    raw=json.dumps(payload).encode();signature='sha256='+hmac.new(b'test-app-secret',raw,hashlib.sha256).hexdigest()
    out=client.post('/api/v1/webhooks/whatsapp',headers={'X-Hub-Signature-256':signature,'Content-Type':'application/json'},content=raw)
    assert out.status_code==200 and out.json()['routed_to_human']==1
    conversations=client.get('/api/v1/conversations',headers=admin).json()
    assert len(conversations)==1 and conversations[0]['human_handoff'] is True
    messages=client.get('/api/v1/conversations/'+conversations[0]['id']+'/messages',headers=admin).json()
    assert messages[0]['body']=='Hello care coordination'
    retry=client.post('/api/v1/webhooks/whatsapp',headers={'X-Hub-Signature-256':signature,'Content-Type':'application/json'},content=raw)
    assert retry.json()['duplicates']==1
    assert len(client.get('/api/v1/conversations/'+conversations[0]['id']+'/messages',headers=admin).json())==1

def test_refresh_rotation_replay_and_logout(context):
    client,auth,_,_=context
    initial=client.post('/api/v1/auth/login',json={'tenant_slug':'a','email':'a@example.test','password':'test_password_12345'})
    assert initial.status_code==200
    old=initial.json()['refresh_token']
    renewed=client.post('/api/v1/auth/refresh',json={'refresh_token':old})
    assert renewed.status_code==200,renewed.text
    new=renewed.json()['refresh_token']
    assert old!=new
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':old}).status_code==401
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':new}).status_code==401
    latest=client.post('/api/v1/auth/login',json={'tenant_slug':'a','email':'a@example.test','password':'test_password_12345'}).json()
    access=latest['access_token'];hdr={'Authorization':'Bearer '+access}
    assert client.get('/api/v1/auth/me',headers=hdr).status_code==200
    assert client.post('/api/v1/auth/logout',headers=hdr).status_code==200
    assert client.get('/api/v1/auth/me',headers=hdr).status_code==401
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':latest['refresh_token']}).status_code==401

def test_invalid_currency_and_cross_tenant_prices(context):
    client,auth,_,_=context;admin=auth('a')
    good={'service_code':'consult','label':'Consultation coordination','currency':'USD','amount_minor':1000,
          'source':'human checked rate card', 'valid_until':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()}
    assert client.post('/api/v1/prices',headers=admin,json=good).status_code==201
    assert client.get('/api/v1/prices',headers=auth('b')).json()==[]
    assert client.post('/api/v1/prices',headers=admin,json=good|{'currency':'US1'}).status_code==422
