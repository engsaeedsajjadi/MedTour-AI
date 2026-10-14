from datetime import datetime,timedelta,timezone

def test_live_and_login(context):
    client,auth,_,_=context
    assert client.get('/api/v1/health/live').json()['production_ready'] is False
    assert client.get('/api/v1/patients').status_code==401
    assert client.post('/api/v1/auth/login',json={'tenant_slug':'a','email':'a@example.test','password':'wrong'}).status_code==401
    assert client.get('/api/v1/dashboard',headers=auth('a')).json()['patients']==0

def test_explicit_consent_required(context):
    client,auth,_,_=context
    a=auth('a')
    p=client.post('/api/v1/patients',headers=a,json={'full_name':'Synthetic Patient','language':'ps'}).json()
    r=client.post('/api/v1/cases',headers=a,json={'patient_id':p['id']})
    assert r.status_code==409
    client.post('/api/v1/consents',headers=a,json={'patient_id':p['id'],'purpose':'intake','accepted':True,'notice_version':'v1'})
    r=client.post('/api/v1/cases',headers=a,json={'patient_id':p['id']})
    assert r.status_code==201,r.text

def test_cross_tenant_blocked(seeded):
    (client,auth,_,_),a,p,c=seeded
    b=auth('b')
    assert client.get('/api/v1/cases',headers=b).json()==[]
    assert client.get('/api/v1/cases/'+c['id'],headers=b).status_code==404
    assert client.get('/api/v1/patients/'+p['id'],headers=b).status_code==404
    assert client.post('/api/v1/referrals',headers=b,json={'case_id':c['id'],'physician_id':'whatever'}).status_code==404
    assert client.post('/api/v1/consents',headers=b,json={'patient_id':p['id'],'purpose':'intake','accepted':True,'notice_version':'v1'}).status_code==404

def test_quote_requires_admin_review(seeded):
    (client,auth,_,_),a,p,c=seeded
    r=client.post('/api/v1/quotes',headers=a,json={'case_id':c['id'],'amount_minor':120000,'currency':'usd','details':'Manual estimate pending clinical review'})
    assert r.status_code==201,r.text
    q=r.json();assert q['status']=='draft' and q['currency']=='USD'
    op=auth('a','operator@example.test')
    assert client.patch('/api/v1/quotes/'+q['id']+'/approve',headers=op).status_code==403
    approved=client.patch('/api/v1/quotes/'+q['id']+'/approve',headers=a)
    assert approved.status_code==200 and approved.json()['status']=='approved'
    assert client.patch('/api/v1/quotes/'+q['id']+'/approve',headers=a).status_code==409

def test_provider_verification_and_booking(seeded):
    (client,auth,_,_),a,p,c=seeded
    dr=client.post('/api/v1/physicians',headers=a,json={'full_name':'Synthetic Doctor','specialty':'cardiology'}).json()
    unverified=client.post('/api/v1/referrals',headers=a,json={'case_id':c['id'],'physician_id':dr['id']})
    assert unverified.status_code==409
    client.patch('/api/v1/physicians/'+dr['id']+'/verification',headers=a,json={'status':'verified'})
    assert client.post('/api/v1/referrals',headers=a,json={'case_id':c['id'],'physician_id':dr['id']}).status_code==201
    future=(datetime.now(timezone.utc)+timedelta(days=4)).isoformat()
    r=client.post('/api/v1/appointments',headers=a,json={'case_id':c['id'],'physician_id':dr['id'],'requested_at':future})
    assert r.status_code==201,r.text
    appoint=r.json();assert appoint['status']=='requested'
    assert client.patch('/api/v1/appointments/'+appoint['id']+'/status',headers=a,json={'status':'confirmed'}).status_code==422
    assert client.patch('/api/v1/appointments/'+appoint['id']+'/status',headers=a,json={'status':'confirmed','reference':'MANUAL-123'}).json()['status']=='confirmed'

def test_travel_not_automatically_confirmed(seeded):
    (client,auth,_,_),a,p,c=seeded
    r=client.post('/api/v1/travel',headers=a,json={'case_id':c['id'],'service_type':'visa','notes':'Patient asked about medical visa'})
    assert r.status_code==201
    item=r.json();assert item['status']=='requested'
    assert client.patch('/api/v1/travel/'+item['id']+'/status',headers=a,json={'status':'confirmed'}).status_code==422

def test_documents_fail_closed(seeded):
    (client,auth,_,_),a,p,c=seeded
    body={'patient_id':p['id'],'case_id':c['id'],'filename':'lab.pdf'}
    assert client.post('/api/v1/documents/upload-ticket',headers=a,json=body).status_code==409
    client.post('/api/v1/consents',headers=a,json={'patient_id':p['id'],'purpose':'medical_documents','accepted':True,'notice_version':'v1'})
    resp=client.post('/api/v1/documents/upload-ticket',headers=a,json=body)
    assert resp.status_code==503 and 'storage' in resp.text.lower()

def test_language_and_emergency_escalation(context):
    client,auth,_,_=context
    a=auth('a')
    assert len(client.get('/api/v1/intake/prompts/ps',headers=a).json()['prompts'])==3
    resp=client.post('/api/v1/intake/evaluate',headers=a,json={'language':'ar','message':'ألم في الصدر'}).json()
    assert resp['emergency_keyword_detected'] is True
    assert resp['human_review_required'] is True
    resp=client.post('/api/v1/intake/evaluate',headers=a,json={'language':'en','message':'I want a consultation'}).json()
    assert resp['emergency_keyword_detected'] is False

def test_case_transition_audit_and_handoff(seeded):
    (client,auth,_,_),a,p,c=seeded
    bad=client.patch('/api/v1/cases/'+c['id']+'/status',headers=a,json={'status':'closed'})
    assert bad.status_code==409
    ok=client.patch('/api/v1/cases/'+c['id']+'/status',headers=a,json={'status':'intake'})
    assert ok.status_code==200
    conv=client.post('/api/v1/conversations',headers=a,json={'patient_id':p['id']}).json()
    hand=client.post('/api/v1/conversations/'+conv['id']+'/handoff',headers=a)
    assert hand.json()['human_handoff'] is True
    client.post('/api/v1/consents',headers=a,json={'patient_id':p['id'],'purpose':'communication','accepted':True,'notice_version':'v1'})
    message=client.post('/api/v1/conversations/'+conv['id']+'/messages',headers=a,json={'body':'Welcome to the coordination service','language':'en'})
    assert message.status_code==201
    assert len(client.get('/api/v1/conversations/'+conv['id']+'/messages',headers=a).json())==1
    logs=client.get('/api/v1/audit',headers=a).json()
    assert any(item['event']=='conversation_handoff' for item in logs)

def test_integration_status_is_honest(context):
    client,auth,_,_=context
    r=client.get('/api/v1/integrations/status',headers=auth('a'))
    assert r.status_code==200
    assert all(x.get('live_connected') is False for x in r.json().values())

def test_ai_draft_fail_closed_without_approval(seeded):
    (client,auth,_,_),a,p,c=seeded
    q=client.post('/api/v1/intake/ai-draft',headers=a,json={'case_id':c['id'],'language':'ps','message':'I need to see a doctor'})
    assert q.status_code==409  # independent opt-in to AI data processing
    client.post('/api/v1/consents',headers=a,json={'patient_id':p['id'],'purpose':'ai_processing','accepted':True,'notice_version':'v1'})
    q=client.post('/api/v1/intake/ai-draft',headers=a,json={'case_id':c['id'],'language':'ps','message':'I need to see a doctor'})
    assert q.status_code==503
    emergency=client.post('/api/v1/intake/ai-draft',headers=a,json={'case_id':c['id'],'language':'en','message':'I have chest pain'})
    assert emergency.status_code==200 and emergency.json()['emergency_keyword_detected'] is True

def test_whatsapp_webhook_disabled_and_signature(context):
    from app.whatsapp import valid_signature
    import hashlib,hmac
    client,auth,_,_=context
    assert client.get('/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=secret&hub.challenge=123').status_code==503
    assert client.post('/api/v1/webhooks/whatsapp',content=b'{}').status_code==503
    body=b'{"entry":[]}'
    signature='sha256='+hmac.new(b'test-secret',body,hashlib.sha256).hexdigest()
    assert valid_signature(body,signature,'test-secret')
    assert not valid_signature(body,signature,'different')
