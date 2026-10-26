"""Section 24 synthetic deterministic orchestration and opt-in provider policy."""
from app.enterprise_models import AIAgentPolicy,AIOrchestrationRun,AIOrchestrationEvent
from app.models import Audit
ROOT="/api/v1/ai-orchestration"
DEMO={"enabled":True,"provider_mode":"deterministic_demo","daily_run_limit":20}

def enable(client,admin,agent="administrative_receptionist",config=None):
    r=client.put(ROOT+"/agents/"+agent,headers=admin,json=config or DEMO)
    assert r.status_code==200,r.text
    return r.json()

def make(client,h,key="TEST-RUN-000001",agent="administrative_receptionist",workflow="general_information",locale="fa"):
    return client.post(ROOT+"/runs",headers=h,json={"request_key":key,
        "agent_key":agent,"workflow":workflow,"locale":locale})

def test_registry_disabled_by_default_no_patient_or_arbitrary_tools(context):
    client,auth,_,Session=context
    admin=auth("a");op=auth("a","operator@example.test")
    catalog=client.get(ROOT+"/catalog",headers=admin)
    assert catalog.status_code==200
    agents=catalog.json()["agents"]
    assert len(agents)==3
    assert all(not x["enabled"] for x in agents)
    assert all("read_approved_knowledge_metadata" in x["tool_permissions"] for x in agents)
    assert catalog.json()["external_tools_enabled"] is False
    assert catalog.json()["auto_send_enabled"] is False
    assert catalog.json()["phi_processing_enabled"] is False
    assert make(client,admin).status_code==409
    assert client.put(ROOT+"/agents/administrative_receptionist",headers=op,json=DEMO).status_code==403
    assert client.put(ROOT+"/agents/arbitrary",headers=admin,json=DEMO).status_code==404
    assert client.put(ROOT+"/agents/administrative_receptionist",headers=admin,
        json=DEMO|{"tool_permissions":["delete_all"],"endpoint":"https://evil.example"}).status_code==422
    enable(client,admin)
    bad=client.post(ROOT+"/runs",headers=op,json={
        "request_key":"OTHER-REQUEST-123",
        "agent_key":"administrative_receptionist","workflow":"general_information",
        "locale":"fa","patient_id":"synthetic-person","prompt":"dump medical history"})
    assert bad.status_code==422
    assert make(client,op,workflow="appointment_process").status_code==422
    assert make(client,op,locale="xx").status_code==422
    with Session() as db:assert db.query(AIOrchestrationRun).count()==0


def test_synthetic_draft_idempotent_and_no_auto_send(context):
    client,auth,_,Session=context
    admin=auth("a");op=auth("a","operator@example.test")
    enable(client,admin)
    r=make(client,op)
    assert r.status_code==201,r.text
    j=r.json()
    assert j["status"]=="pending_human_review"
    assert j["mode"]=="deterministic_demo"
    assert "نتیجه" not in j["request_key"]
    assert j["sent"] is False and j["clinical_decision"] is False
    assert j["patient_data_processed"] is False and j["review_required"] is True
    assert j["knowledge_reference_ids"]==[]
    assert make(client,op).json()["deduplicated"] is True
    assert make(client,op,workflow="document_safety").status_code==409
    assert client.get(ROOT+"/runs/"+j["id"],headers=op).json()["id"]==j["id"]
    assert client.get(ROOT+"/runs",headers=op).json()["items"][0]["id"]==j["id"]
    blocked=client.post(ROOT+"/runs/"+j["id"]+"/review",headers=op,json={
        "decision":"approve_internal","evidence_reference":"SYNTH-OPERATOR-1"})
    assert blocked.status_code==403
    approved=client.post(ROOT+"/runs/"+j["id"]+"/review",headers=admin,json={
        "decision":"approve_internal","evidence_reference":"SYNTH-HUMAN-REVIEW-1"})
    assert approved.status_code==200,approved.text
    assert approved.json()["status"]=="approved_for_internal_reference"
    assert approved.json()["external_message_sent"] is False
    assert approved.json()["financial_action_taken"] is False
    assert client.post(ROOT+"/runs/"+j["id"]+"/review",headers=admin,json={
        "decision":"reject","evidence_reference":"SYNTH-REPEAT-001"}).status_code==409
    h=client.get(ROOT+"/runs/"+j["id"]+"/events",headers=admin).json()["items"]
    assert len(h)==2
    with Session() as db:
        assert db.query(AIOrchestrationEvent).count()==2
        assert db.query(Audit).filter(Audit.event=="ai_orchestration_draft_created").count()==1
        assert db.query(AIOrchestrationRun).first().result_text==j["display_text"]


def test_same_user_cannot_review_and_tenant_boundary(context):
    client,auth,_,Session=context
    admin=auth("a");outsider=auth("b")
    enable(client,admin)
    run=make(client,admin).json()
    assert client.post(ROOT+"/runs/"+run["id"]+"/review",headers=admin,json={
        "decision":"approve_internal","evidence_reference":"SYNTH-SELF-APPROVAL"}).status_code==409
    assert client.get(ROOT+"/runs/"+run["id"],headers=outsider).status_code==404
    assert client.get(ROOT+"/runs/"+run["id"]+"/events",headers=outsider).status_code==404
    assert client.get(ROOT+"/runs",headers=outsider).json()["items"]==[]
    assert make(client,outsider).status_code==409
    assert client.put(ROOT+"/agents/administrative_receptionist",headers=outsider,json=DEMO).status_code==200
    theirs=make(client,outsider)
    assert theirs.status_code==201
    assert theirs.json()["id"]!=run["id"]
    assert client.get(ROOT+"/runs",headers=admin).json()["items"][0]["id"]==run["id"]


def test_budget_disable_and_reviewer_recheck(context):
    client,auth,_,Session=context
    admin=auth("a");op=auth("a","operator@example.test")
    enable(client,admin,config=DEMO|{"daily_run_limit":1})
    one=make(client,op).json()
    assert make(client,op,key="TEST-RUN-000002").status_code==429
    disabled=client.put(ROOT+"/agents/administrative_receptionist",
        headers=admin,json=DEMO|{"enabled":False})
    assert disabled.status_code==200
    assert make(client,op,key="TEST-RUN-000003").status_code==409
    assert client.post(ROOT+"/runs/"+one["id"]+"/review",headers=admin,json={
        "decision":"approve_internal","evidence_reference":"SYNTH-DISABLED-1"}).status_code==409
    assert client.post(ROOT+"/runs/"+one["id"]+"/review",headers=admin,json={
        "decision":"reject","evidence_reference":"SYNTH-REJECTED-1"}).status_code==200
    assert client.get(ROOT+"/runs/"+one["id"],headers=op).json()["status"]=="rejected"


def test_only_approved_knowledge_ids_no_raw_article_content(context):
    client,auth,_,Session=context
    admin=auth("a");op=auth("a","operator@example.test")
    approved=client.post("/api/v1/knowledge",headers=op,json={
        "locale":"en","title":"General administrative knowledge",
        "body":"Private synthetic test article: do not send to AI provider"}).json()["id"]
    unapproved=client.post("/api/v1/knowledge",headers=op,json={
        "locale":"en","title":"Other administrative knowledge",
        "body":"Unapproved synthetic internal information"}).json()["id"]
    assert client.patch("/api/v1/knowledge/"+approved+"/approve",headers=admin).status_code==200
    enable(client,admin,agent="knowledge_assistant")
    res=make(client,op,key="KNOWLEDGE-RUN-100",agent="knowledge_assistant",
        workflow="knowledge_discovery",locale="en")
    assert res.status_code==201,res.text
    j=res.json()
    assert approved in j["knowledge_reference_ids"]
    assert unapproved not in j["knowledge_reference_ids"]
    assert "Private synthetic test article" not in str(j)
    assert "Unapproved synthetic" not in str(j)


def test_provider_policy_fails_closed_and_output_quality_rejected(context,monkeypatch):
    import app.ai_orchestration as orch
    client,auth,_,Session=context
    admin=auth("a");op=auth("a","operator@example.test")
    config=DEMO|{"provider_mode":"approved_provider"}
    assert client.put(ROOT+"/agents/administrative_receptionist",
        headers=admin,json=config).status_code==503
    monkeypatch.setattr(orch,"provider_available",lambda:True)
    enable(client,admin,config=config)
    capture=[]
    def provider(prompt,locale):
        capture.append((prompt,locale))
        return {"message":"Guaranteed cure and medical diagnosis for all patients",
                "human_review_required":True}
    monkeypatch.setattr(orch,"provider_draft",provider)
    bad=make(client,op,key="EXTERNAL-RUN-100")
    assert bad.status_code==201,bad.text
    j=bad.json()
    assert j["status"]=="blocked_quality_gate"
    assert "Guaranteed cure" not in j["display_text"]
    assert len(capture)==1
    assert "patient" not in capture[0][0].lower() or "patient case details" in capture[0][0].lower()
    assert client.post(ROOT+"/runs/"+j["id"]+"/review",headers=admin,json={
        "decision":"approve_internal","evidence_reference":"SYNTH-BAD-QUALITY"}).status_code==409
    assert client.post(ROOT+"/runs/"+j["id"]+"/review",headers=admin,json={
        "decision":"reject","evidence_reference":"SYNTH-REJECT-QUALITY"}).status_code==200
    monkeypatch.setattr(orch,"provider_draft",lambda p,l:{
        "message":"General administrative inquiries require a human coordinator."})
    good=make(client,op,key="EXTERNAL-RUN-101")
    assert good.status_code==201 and good.json()["mode"]=="approved_provider"
    assert good.json()["status"]=="pending_human_review"
    monkeypatch.setattr(orch,"provider_available",lambda:False)
    assert make(client,op,key="EXTERNAL-RUN-102").status_code==503


def test_environment_gate_and_no_provider_calls_without_optin(context,monkeypatch):
    import app.ai_orchestration as orch
    client,auth,_,_=context
    admin=auth("a")
    enable(client,admin)
    monkeypatch.setenv("APP_ENV","staging")
    assert make(client,admin).status_code==503
    assert client.put(ROOT+"/agents/administrative_receptionist",headers=admin,
        json=DEMO).status_code==503
    monkeypatch.setenv("APP_ENV","test")
    assert make(client,admin).status_code==201
    monkeypatch.setenv("AI_PROVIDER_APPROVED","false")
    assert client.get(ROOT+"/catalog",headers=admin).json()["real_ai_provider_ready"] is False
