"""Section 28 synthetic privacy workflow & tenant isolation."""
def test_privacy_registry_role_tenant_and_transitions(context):
    client, auth, tids, Session = context
    a, b = auth("a"), auth("b")
    patient=client.post("/api/v1/patients",headers=a,json={
        "full_name":"Synthetic only","language":"en"}).json()
    base="/api/v1/privacy/requests"
    assert client.post(base,headers=b,json={"patient_id":patient["id"],"request_type":"access"}).status_code==404
    row=client.post(base,headers=a,json={"patient_id":patient["id"],"request_type":"erasure"})
    assert row.status_code==201,row.text
    data=row.json();assert data["status"]=="pending_identity"
    assert data["automatic_export_or_deletion"] is False
    id=data["id"]
    assert client.get(base+"/"+id,headers=b).status_code==404
    assert client.get(base,headers=b).json()["items"]==[]
    operator=auth("a","operator@example.test")
    assert client.get(base,headers=operator).status_code==403
    assert client.post(base,headers=operator,json={"patient_id":patient["id"],"request_type":"erasure"}).status_code==403
    assert client.post(base+"/"+id+"/review",headers=a,json={"decision":"closed_manual"}).status_code==409
    assert client.post(base+"/"+id+"/review",headers=a,json={"decision":"identity_verified"}).json()["status"]=="pending_legal_review"
    assert client.post(base+"/"+id+"/review",headers=a,json={"decision":"legal_hold"}).json()["status"]=="legal_hold"
    assert client.post(base+"/"+id+"/review",headers=b,json={"decision":"closed_manual"}).status_code==404
    assert client.post(base+"/"+id+"/review",headers=a,json={"decision":"closed_manual"}).json()["status"]=="closed_manual"
    assert client.post(base+"/"+id+"/review",headers=a,json={"decision":"closed_manual"}).status_code==409
    assert client.get("/api/v1/patients",headers=a).json()[0]["id"]==patient["id"]
    events=client.get("/api/v1/audit",headers=a).json()
    assert any(x["event"]=="privacy_request_opened" and x["entity_id"]==id for x in events)

def test_privacy_input_is_strict(context):
    client, auth, _, _ = context
    a=auth("a")
    response=client.post("/api/v1/privacy/requests",headers=a,json={
        "patient_id":"synthetic","request_type":"unknown"})
    assert response.status_code==422
    response=client.post("/api/v1/privacy/requests",headers=a,json={
        "patient_id":"synthetic","request_type":"access","medical_record":"DO NOT STORE"})
    assert response.status_code==422
