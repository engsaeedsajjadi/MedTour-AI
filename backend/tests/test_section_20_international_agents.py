"""Section 20: synthetic agent governance, no lawful payout or patient PHI."""
ROOT="/api/v1/agent-network"
PASSWORD="Agent-Only-Synthetic-Password-20"

def agent_create(client,admin,name="Synthetic Agency 20"):
    r=client.post("/api/v1/agents",headers=admin,json={"name":name,"country":"AF"})
    assert r.status_code==201,r.text
    return r.json()["id"]

def agreement(client,admin,id,code="CONTRACT-SYNTH-20",cap=1000):
    r=client.post(ROOT+"/agents/"+id+"/agreements",headers=admin,json={
        "contract_key":code,"jurisdiction":"AF","currency":"USD",
        "scope":"nonclinical_logistics","max_budget_minor":cap})
    assert r.status_code==201,r.text
    return r.json()["id"]

def review(client,admin,id):
    r=client.post(ROOT+"/agreements/"+id+"/review",headers=admin,json={
        "decision":"administratively_reviewed","document_reference":"MOCK-DOC-REF-20"})
    assert r.status_code==200,r.text
    assert not r.json()["binding_contract_verified"]
    assert not r.json()["compensation_payable"]

def provision(client,admin,id,email="agent20@example.com"):
    return client.post(ROOT+"/agents/"+id+"/account",headers=admin,json={
        "email":email,"password":PASSWORD})

def agent_login(client):
    r=client.post("/api/v1/auth/login",json={
        "tenant_slug":"a","email":"agent20@example.com","password":PASSWORD})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["access_token"]},r.json()["refresh_token"]

def give(client,admin,purpose,patient):
    r=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":patient["id"],"purpose":purpose,
        "accepted":True,"notice_version":"v20-synthetic"})
    assert r.status_code==201,r.text

def intent(client,auth,key="REFERRAL-INTENT-20",campaign="CAMPAIGN20"):
    return client.post(ROOT+"/portal/referrals",headers=auth,json={
        "request_key":key,"channel":"web","campaign_code":campaign})

def setup(client,admin):
    a=agent_create(client,admin)
    ag=agreement(client,admin,a)
    review(client,admin,ag)
    p=provision(client,admin,a)
    assert p.status_code==201,p.text
    assert p.json()["role"]=="agent"
    return a,ag

def test_full_agent_portal_least_privilege_and_consent(seeded):
    (client,auth,_,Session),admin,patient,case=seeded
    a,contract=setup(client,admin)
    agent,_=agent_login(client)
    portal=client.get(ROOT+"/portal/me",headers=agent)
    assert portal.status_code==200
    assert portal.json()["agent_id"]==a
    assert portal.json()["clinical_data_access"] is False
    assert portal.json()["commission_payments_enabled"] is False
    for url in ("/api/v1/patients","/api/v1/cases","/api/v1/agents",
                "/api/v1/lead-sources","/api/v1/finance/entries",
                ROOT+"/agents/"+a+"/referrals"):
        assert client.get(url,headers=agent).status_code==403,url
    assert client.get(ROOT+"/portal/referrals",headers=admin).status_code==403
    bad=intent(client,agent,key="PHI-SENSITIVE-20",campaign="CAMPAIGN20")
    assert bad.status_code==201,bad.text
    created=intent(client,agent)
    assert created.status_code==201,created.text
    ref=created.json()
    assert "patient_id" not in ref and "case_id" not in ref and "full_name" not in ref
    assert intent(client,agent).json()["reused"] is True
    assert intent(client,agent,campaign="DIFFERENT").status_code==409
    assert client.post(ROOT+"/portal/referrals",headers=agent,json={
        "request_key":"OTHER-PHI-20","channel":"web",
        "campaign_code":"GOOD20","patient_name":"Never allowed"}).status_code==422
    assert client.post(ROOT+"/referrals/"+ref["id"]+"/attribute",headers=admin,
        json={"patient_id":patient["id"]}).status_code==409
    give(client,admin,"agent_referral",patient)
    linked=client.post(ROOT+"/referrals/"+ref["id"]+"/attribute",headers=admin,
        json={"patient_id":patient["id"]})
    assert linked.status_code==200,linked.text
    assert linked.json()["patient_id"]==patient["id"]
    assert client.post(ROOT+"/referrals/"+ref["id"]+"/attribute",headers=admin,
        json={"patient_id":patient["id"]}).status_code==409
    listed=client.get(ROOT+"/portal/referrals",headers=agent).json()["items"]
    assert all("patient_id" not in x for x in listed)
    assert any(x["status"]=="attributed" for x in listed)
    with Session() as db:
        from app.enterprise_models import LeadSource
        rows=db.query(LeadSource).all()
        assert len(rows)==1 and rows[0].agent_id==a and rows[0].patient_id==patient["id"]


def test_consent_withdrawal_and_nonreactivation(seeded):
    (client,auth,_,Session),admin,patient,_=seeded
    a,_=setup(client,admin)
    agent,_=agent_login(client)
    ref=intent(client,agent).json()["id"]
    give(client,admin,"agent_referral",patient)
    assert client.post(ROOT+"/referrals/"+ref+"/attribute",headers=admin,
        json={"patient_id":patient["id"]}).status_code==200
    one_time=client.post("/api/v1/consent-links/"+patient["id"]+"/agent_referral",
        headers=admin).json()["token"]
    rev=client.post("/api/v1/consent-links/respond",json={
        "token":one_time,"accepted":False,"notice_version":"v20-synthetic"})
    assert rev.status_code==201,rev.text
    records=client.get(ROOT+"/portal/referrals",headers=agent).json()["items"]
    assert records[0]["status"]=="blocked"
    assert "patient_id" not in records[0]
    from app.enterprise_models import LeadSource
    with Session() as db:
        link=db.query(LeadSource).filter(LeadSource.patient_id==patient["id"]).one()
        assert link.agent_id is None
        assert link.source=="agent_referral_revoked"
    give(client,admin,"agent_referral",patient)
    assert client.post(ROOT+"/referrals/"+ref+"/attribute",headers=admin,
        json={"patient_id":patient["id"]}).status_code==409


def test_contract_control_and_blocked_cost_drafts(seeded):
    (client,auth,_,Session),admin,_,_=seeded
    a=agent_create(client,admin)
    ag=agreement(client,admin,a,cap=1000)
    assert provision(client,admin,a).status_code==409
    assert client.post(ROOT+"/agents/"+a+"/agreements",headers=admin,json={
        "contract_key":"CONTRACT-SYNTH-20","jurisdiction":"IR","currency":"USD",
        "scope":"nonclinical_logistics","max_budget_minor":1000}).status_code==409
    review(client,admin,ag)
    body={"agreement_id":ag,"draft_key":"COST-DEMO-0001",
          "activity_reference":"NONCLINIC-ACT-01","amount_minor":600}
    r=client.post(ROOT+"/agents/"+a+"/commercial-drafts",headers=admin,json=body)
    assert r.status_code==201,r.text
    assert r.json()["status"]=="blocked_legal_review"
    assert not r.json()["payout_authorized"]
    again=client.post(ROOT+"/agents/"+a+"/commercial-drafts",headers=admin,json=body)
    assert again.status_code==201 and again.json()["reused"]
    assert client.post(ROOT+"/agents/"+a+"/commercial-drafts",headers=admin,
        json=body|{"amount_minor":400}).status_code==409
    assert client.post(ROOT+"/agents/"+a+"/commercial-drafts",headers=admin,
        json=body|{"draft_key":"COST-DEMO-0002","amount_minor":401}).status_code==409
    assert client.post(ROOT+"/agents/"+a+"/commercial-drafts",headers=admin,
        json=body|{"draft_key":"COST-DEMO-0003","amount_minor":400}).status_code==201
    xs=client.get(ROOT+"/agents/"+a+"/commercial-drafts",headers=admin).json()
    assert xs["payouts_enabled"] is False
    assert xs["per_patient_commissions_enabled"] is False
    assert all(x["payout_authorized"] is False for x in xs["items"])
    h=client.get(ROOT+"/agents/"+a+"/history",headers=admin)
    assert h.status_code==200 and len(h.json()["items"])>=3


def test_disable_account_blocks_refresh_and_portal(seeded):
    (client,auth,_,_),admin,_,_=seeded
    a,ag=setup(client,admin)
    agent,refresh=agent_login(client)
    assert client.get(ROOT+"/portal/me",headers=agent).status_code==200
    result=client.post(ROOT+"/agents/"+a+"/disable",headers=admin)
    assert result.status_code==200
    assert result.json()["linked_accounts_disabled"]==1
    assert client.get(ROOT+"/portal/me",headers=agent).status_code==401
    assert client.post("/api/v1/auth/refresh",json={"refresh_token":refresh}).status_code==401
    assert client.post("/api/v1/auth/login",json={
        "tenant_slug":"a","email":"agent20@example.com","password":PASSWORD}).status_code==401
    assert client.post(ROOT+"/agents/"+a+"/agreements",headers=admin,json={
        "contract_key":"NEW-CONTRACT-20","jurisdiction":"AF","currency":"USD",
        "max_budget_minor":10}).status_code==409


def test_tenant_isolation_and_agent_cannot_hijack_other_id(seeded):
    (client,auth,_,_),admin,patient,_=seeded
    a,ag=setup(client,admin)
    outsider=auth("b")
    assert client.get(ROOT+"/agents/"+a+"/agreements",headers=outsider).status_code==404
    assert client.post(ROOT+"/agents/"+a+"/account",headers=outsider,json={
        "email":"someone@example.com","password":PASSWORD}).status_code==404
    assert client.get(ROOT+"/agents/"+a+"/referrals",headers=outsider).status_code==404
    assert client.post(ROOT+"/agents/"+a+"/commercial-drafts",headers=outsider,json={
        "draft_key":"COST-FOREIGN-20","agreement_id":ag,
        "activity_reference":"ACTIVITY-OTHER-20","amount_minor":10}).status_code==404
    agent,_=agent_login(client)
    assert client.post(ROOT+"/agents/"+a+"/disable",headers=agent).status_code==403
    assert client.post("/api/v1/lead-sources",headers=admin,json={
        "patient_id":patient["id"],"agent_id":a,"source":"manual"}).status_code==409
    assert client.post("/api/v1/lead-sources",headers=admin,json={
        "patient_id":patient["id"],"source":"direct"}).status_code==201


def test_agent_identity_provision_rejects_duplicate_and_bad_inputs(seeded):
    (client,auth,_,_),admin,_,_=seeded
    a=agent_create(client,admin)
    ag=agreement(client,admin,a)
    assert client.post(ROOT+"/agents/"+a+"/agreements",headers=admin,json={
        "contract_key":"SHORT","jurisdiction":"AF","currency":"USD",
        "scope":"nonclinical_marketing","max_budget_minor":0}).status_code==422
    review(client,admin,ag)
    first=provision(client,admin,a)
    assert first.status_code==201,first.text
    assert "password" not in first.json()
    assert provision(client,admin,a).status_code==409
    operator=auth("a","operator@example.test")
    assert client.post(ROOT+"/agents/"+a+"/agreements",headers=operator,json={
        "contract_key":"ANOTHER-CONTRACT-20","jurisdiction":"AF","currency":"USD",
        "max_budget_minor":0}).status_code==403


def test_legacy_agency_fee_accounting_remains_closed(seeded):
    (client,auth,_,_),admin,_,case=seeded
    attempted=client.post("/api/v1/finance/entries",headers=admin,json={
        "case_id":case["id"],"entry_type":"agency_fee",
        "currency":"USD","amount_minor":200,
        "source_reference":"NONCLINICAL-ESTIMATE-20"})
    assert attempted.status_code==409
    assert client.get("/api/v1/finance/entries",headers=admin).json()==[]


def test_same_tenant_agents_cannot_read_each_others_tracking(seeded):
    (client,auth,_,_),admin,_,_=seeded
    first,_=setup(client,admin)
    first_user,_=agent_login(client)
    referral=intent(client,first_user).json()
    second=agent_create(client,admin,"Another Synthetic Agency 20")
    other_ag=agreement(client,admin,second,code="CONTRACT-SECOND-20")
    review(client,admin,other_ag)
    other_provision=provision(client,admin,second,email="agent21@example.com")
    assert other_provision.status_code==201,other_provision.text
    response=client.post("/api/v1/auth/login",json={
        "tenant_slug":"a","email":"agent21@example.com","password":PASSWORD})
    assert response.status_code==200,response.text
    second_user={"Authorization":"Bearer "+response.json()["access_token"]}
    assert client.get(ROOT+"/portal/referrals",headers=second_user).json()["items"]==[]
    assert client.get(ROOT+"/portal/me",headers=second_user).json()["agent_id"]==second
    assert client.get(ROOT+"/portal/me",headers=first_user).json()["agent_id"]==first
    assert client.get(ROOT+"/portal/referrals",headers=first_user).json()["items"][0]["id"]==referral["id"]
    assert client.get(ROOT+"/agents/"+first+"/referrals",headers=second_user).status_code==403
