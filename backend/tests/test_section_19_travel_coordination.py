"""Section 19 synthetic transport/interpreter workflows; no real provider actions."""
from datetime import datetime,timedelta,timezone
from app.enterprise_models import TravelAssignment,TravelResourceWindow,TravelAssignmentEvent
ROOT="/api/v1/travel-coordination"
REF="SYNTHETIC-REVIEW-19"
CLOCK_ANCHOR=datetime.now(timezone.utc).replace(microsecond=0)


def times(start_days=10,hours=2):
    a=CLOCK_ANCHOR+timedelta(days=start_days)
    return a.isoformat(),(a+timedelta(hours=hours)).isoformat()


def consent(client,headers,patient,purpose,accepted=True):
    r=client.post("/api/v1/consents",headers=headers,json={
        "patient_id":patient["id"],"purpose":purpose,"accepted":accepted,
        "notice_version":"v19-synthetic"})
    assert r.status_code==201,r.text


def resource(client,user,kind="vehicle",seats=3,language=None):
    r=client.post(ROOT+"/resources",headers=user,json={
        "kind":kind,"label":"Synthetic Partner Desk","city":"Tehran",
        "seats":seats,"language":language})
    assert r.status_code==201,r.text
    return r.json()["id"]


def window(client,user,res,start=None,end=None):
    a,b=times() if start is None else (start,end)
    return client.post(ROOT+"/resources/"+res+"/windows",headers=user,json={
        "starts_at":a,"ends_at":b,"reference":"LOCAL-WINDOW-19"})


def req(client,user,c,res,key="SYNTH-REQUEST-19",kind="airport_pickup",start=None,end=None,**other):
    a,b=times() if start is None else (start,end)
    body={"request_key":key,"resource_id":res,"kind":kind,
          "starts_at":a,"ends_at":b,"passengers":2,
          "language":None,"origin_zone":"airport","destination_zone":"hotel",**other}
    return client.post(ROOT+"/cases/"+c["id"]+"/requests",headers=user,json=body)


def action(client,user,id,act,key,supplier=None):
    return client.post(ROOT+"/requests/"+id+"/transition",headers=user,json={
        "step_key":key,"action":act,"reference":REF,"supplier_name":supplier})


def test_vehicle_lifecycle_audit_and_no_verified_dispatch(seeded):
    (client,auth,_,Session),admin,p,c=seeded
    assert req(client,admin,c,"unknown").status_code==409
    consent(client,admin,p,"transport_coordination")
    rid=resource(client,admin)
    assert window(client,admin,rid).status_code==201
    r=req(client,admin,c,rid)
    assert r.status_code==201,r.text
    x=r.json()
    assert x["external_dispatch_verified"] is False
    assert req(client,admin,c,rid).json()["reused"] is True
    op=auth("a","operator@example.test")
    assert action(client,op,x["id"],"allocate_internally","BAD-OPERATOR-19").status_code==403
    assert action(client,admin,x["id"],"report_provider_ack","EARLY-ACK-19","Synthetic Vendor").status_code==409
    for name,key,desk in [
        ("allocate_internally","LOCAL-ALLOCATE-19",None),
        ("report_provider_contact","LOCAL-CONTACT-19","Synthetic Vendor"),
        ("report_provider_ack","LOCAL-ACK-19","Synthetic Vendor")
    ]:
        z=action(client,admin,x["id"],name,key,desk)
        assert z.status_code==200,z.text
    assert z.json()["status"]=="provider_ack_reported"
    assert z.json()["supplier_name"]=="Synthetic Vendor"
    assert z.json()["external_dispatch_verified"] is False
    repeated=action(client,admin,x["id"],"report_provider_ack","LOCAL-ACK-19","Synthetic Vendor")
    assert repeated.status_code==200 and repeated.json()["reused"] is True
    assert client.get(ROOT+"/requests/"+x["id"]+"/history",headers=admin).json()["items"][-1]["action"]=="report_provider_ack"
    with Session() as db:
        assert db.query(TravelAssignmentEvent).count()==3


def test_resource_conflicts_half_open_windows_and_revoke(seeded):
    (client,auth,_,_),admin,p,c=seeded
    consent(client,admin,p,"transport_coordination")
    rid=resource(client,admin)
    assert window(client,admin,rid).status_code==201
    assert window(client,admin,rid).status_code==409
    a=req(client,admin,c,rid,key="STAY-FIRST-19").json()["id"]
    b=req(client,admin,c,rid,key="STAY-SECOND-19").json()["id"]
    assert action(client,admin,a,"allocate_internally","ALLOC-FIRST-19").status_code==200
    assert action(client,admin,b,"allocate_internally","ALLOC-SECOND-19").status_code==409
    w=client.get(ROOT+"/resources/"+rid+"/windows",headers=admin).json()["items"][0]
    assert client.post(ROOT+"/windows/"+w["id"]+"/revoke",headers=admin).status_code==409
    assert action(client,admin,a,"cancel","CANCEL-FIRST-19").status_code==200
    assert action(client,admin,b,"allocate_internally","ALLOC-SECOND-19").status_code==200
    # Same shared window permits back-to-back requests with no overlapping time.
    origin=datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=12)
    next_rid=resource(client,admin)
    start=origin.isoformat()
    middle=(origin+timedelta(hours=1)).isoformat()
    end=(origin+timedelta(hours=2)).isoformat()
    assert window(client,admin,next_rid,start,end).status_code==201
    for i,(a,b) in enumerate([(start,middle),(middle,end)]):
        item=req(client,admin,c,next_rid,key="BACK-TO-BACK-19-"+str(i),start=a,end=b)
        assert item.status_code==201,item.text
        assert action(client,admin,item.json()["id"],"allocate_internally",
                      "ALLOCATION-BOUNDARY-"+str(i)).status_code==200


def test_interpreter_language_and_consent_separation(seeded):
    (client,auth,_,_),admin,p,c=seeded
    consent(client,admin,p,"transport_coordination")
    interpreter=resource(client,admin,kind="interpreter",seats=1,language="ar")
    assert window(client,admin,interpreter).status_code==201
    payload={"kind":"interpreter_session","passengers":1,"language":"ar",
             "origin_zone":"not_applicable","destination_zone":"not_applicable"}
    assert req(client,admin,c,interpreter,**payload).status_code==409
    consent(client,admin,p,"interpreter_coordination")
    invalid=req(client,admin,c,interpreter,kind="interpreter_session",passengers=1,
           language="fa",origin_zone="not_applicable",destination_zone="not_applicable")
    assert invalid.status_code==422
    good=req(client,admin,c,interpreter,**payload)
    assert good.status_code==201,good.text
    assert good.json()["interpreter_credential_verified"] is False
    assert action(client,admin,good.json()["id"],"allocate_internally","ALLOC-INTERPRETER-19").status_code==200
    consent(client,admin,p,"transport_coordination",accepted=False)
    listed=client.get(ROOT+"/cases/"+c["id"]+"/requests",headers=admin).json()["items"]
    assert len(listed)==1 and listed[0]["kind"]=="interpreter_session"


def test_revoke_consent_blocks_and_preserves_allocation(seeded):
    (client,auth,_,Session),admin,p,c=seeded
    consent(client,admin,p,"transport_coordination")
    rid=resource(client,admin)
    win=window(client,admin,rid).json()["id"]
    first=req(client,admin,c,rid).json()["id"]
    second=req(client,admin,c,rid,key="SECOND-CONSENT-19").json()["id"]
    assert action(client,admin,first,"allocate_internally","ALLOC-REVOKED-19").status_code==200
    token=client.post("/api/v1/consent-links/"+p["id"]+"/transport_coordination",
        headers=admin).json()["token"]
    denied=client.post("/api/v1/consent-links/respond",json={
        "token":token,"notice_version":"v19-synthetic","accepted":False})
    assert denied.status_code==201,denied.text
    with Session() as db:
        assert db.query(TravelAssignment).filter(TravelAssignment.id==first).one().status=="blocked"
    consent(client,admin,p,"transport_coordination")
    assert action(client,admin,first,"cancel","BLOCKED-AFTER-CONSENT-19").status_code==409
    assert req(client,admin,c,rid).status_code==409
    assert action(client,admin,second,"allocate_internally","REUSE-BLOCKED-19").status_code==409
    assert client.post(ROOT+"/windows/"+win+"/revoke",headers=admin).status_code==409
    fresh=req(client,admin,c,rid,key="FRESH-AFTER-WITHDRAW-19")
    assert fresh.status_code==201
    assert action(client,admin,fresh.json()["id"],"allocate_internally","BLOCKED-STOCK-19").status_code==409


def test_invalid_inputs_roles_and_legacy_bypass(seeded):
    (client,auth,_,_),admin,p,c=seeded
    consent(client,admin,p,"transport_coordination")
    rid=resource(client,admin)
    assert req(client,admin,c,rid,passport="SENSITIVE").status_code==422
    assert req(client,admin,c,rid,passengers=5).status_code==422
    assert req(client,admin,c,rid,origin_zone="hotel").status_code==422
    assert req(client,admin,c,rid,origin_zone="hotel",destination_zone="hotel").status_code==422
    assert req(client,admin,c,rid,start="2026-11-01T10:00:00",
               end="2026-11-01T11:00:00").status_code==422
    r=req(client,admin,c,rid)
    assert r.status_code==201
    assert req(client,admin,c,rid,passengers=1).status_code==409
    old=client.post("/api/v1/travel",headers=admin,json={
        "case_id":c["id"],"service_type":"transport"}).json()
    assert client.patch("/api/v1/travel/"+old["id"]+"/status",headers=admin,
        json={"status":"confirmed","reference":REF}).status_code==409
    operation=client.post("/api/v1/operations",headers=admin,json={
        "kind":"interpreter","case_id":c["id"],"title":"Synthetic translation"}).json()
    for state in ["in_review","awaiting_external"]:
        assert client.post("/api/v1/operations/"+operation["id"]+"/transition",
             headers=admin,json={"status":state}).status_code==200
    assert client.post("/api/v1/operations/"+operation["id"]+"/transition",
        headers=admin,json={"status":"confirmed","reference":REF}).status_code==409


def test_cross_tenant_and_due_queue(seeded):
    (client,auth,_,_),admin,p,c=seeded
    consent(client,admin,p,"transport_coordination")
    rid=resource(client,admin)
    window(client,admin,rid)
    item=req(client,admin,c,rid)
    assert item.status_code==201
    outsider=auth("b")
    assert client.get(ROOT+"/resources",headers=outsider).json()["items"]==[]
    assert client.get(ROOT+"/resources/"+rid+"/windows",headers=outsider).status_code==404
    assert client.get(ROOT+"/cases/"+c["id"]+"/requests",headers=outsider).status_code==404
    assert client.get(ROOT+"/requests/"+item.json()["id"]+"/history",headers=outsider).status_code==404
    assert action(client,outsider,item.json()["id"],"allocate_internally","FOREIGN-CALL-19").status_code==404
    assert len(client.get(ROOT+"/due",headers=admin).json()["items"])==0  # scheduled in 10 days
    assert client.get(ROOT+"/due",headers=outsider).json()["items"]==[]
