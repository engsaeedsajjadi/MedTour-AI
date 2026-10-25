"""Section 18 synthetic accommodation security and allocation regressions."""
from datetime import datetime, timedelta, timezone
from app.enterprise_models import AccommodationProperty, AccommodationStay, AccommodationInventory, AccommodationEvent
ROOT="/api/v1/accommodation"


def allow(client, admin, patient_id):
    r=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":patient_id,"purpose":"accommodation_coordination",
        "accepted":True,"notice_version":"v18-synthetic"})
    assert r.status_code==201,r.text


def days(start=10,nights=4):
    today=datetime.now(timezone.utc).date()
    return ((today+timedelta(days=start)).isoformat(),
            (today+timedelta(days=start+nights)).isoformat())


def setup(client,admin,patient_id,rooms=2):
    allow(client,admin,patient_id)
    h=client.post(ROOT+"/properties",headers=admin,json={
       "name":"Synthetic Hotel for Tests", "city":"Tehran"})
    assert h.status_code==201,h.text
    pid=h.json()["id"]
    first,last=days()
    r=client.post(ROOT+"/properties/"+pid+"/inventory",headers=admin,json={
       "room_type":"double","starts_on":first,"ends_on":last,
       "proposed_rooms":rooms,"reference":"LOCAL-INVENTORY-18"})
    assert r.status_code==201,r.text
    return pid,r.json()["id"]


def request(client,user,case_id,property_id,key="STAY-SYNTHETIC-18",**kwargs):
    first,last=days()
    return client.post(ROOT+"/cases/"+case_id+"/stays",headers=user,json={
       "request_key":key,"property_id":property_id,"room_type":"double",
       "starts_on":first,"ends_on":last,"rooms_requested":1,"guests":2,**kwargs})


def move(client,user,stay_id,action,key,**kwargs):
    return client.post(ROOT+"/stays/"+stay_id+"/transition",headers=user,json={
       "step_key":key,"action":action,"reference":"LOCAL-REVIEW-18",**kwargs})


def test_end_to_end_manual_coordination_never_certifies_real_booking(seeded):
    (client,auth,_,Session),admin,p,c=seeded
    assert client.get(ROOT+"/cases/"+c["id"]+"/stays",headers=admin).status_code==409
    assert client.post(ROOT+"/properties",headers=auth("a","operator@example.test"),
       json={"name":"Unauthorized Hotel","city":"Tehran"}).status_code==403
    property_id,inventory_id=setup(client,admin,p["id"])
    stay=request(client,admin,c["id"],property_id)
    assert stay.status_code==201,stay.text
    sid=stay.json()["id"]
    assert stay.json()["provider_booking_independently_verified"] is False
    replay=request(client,admin,c["id"],property_id)
    assert replay.status_code==201 and replay.json()["reused"] is True
    op=auth("a","operator@example.test")
    assert move(client,op,sid,"hold_internally","UNAUTHORIZED-HOLD-18").status_code==403
    assert move(client,admin,sid,"report_provider_request","TOO-EARLY-REQUEST-18",
                supplier_name="Synthetic Supplier").status_code==409
    held=move(client,admin,sid,"hold_internally","HOLD-INTERNAL-18")
    assert held.status_code==200,held.text
    assert held.json()["inventory_id"]==inventory_id
    assert held.json()["status"]=="internally_held"
    sent=move(client,admin,sid,"report_provider_request","EXTERNAL-REQUEST-18",
              supplier_name="Synthetic Supplier")
    assert sent.status_code==200 and sent.json()["status"]=="external_request_reported"
    assert move(client,admin,sid,"report_provider_confirmation","NO-NAME-18").status_code==422
    confirmation=move(client,admin,sid,"report_provider_confirmation","EXTERNAL-REPORTED-18",
                      supplier_name="Synthetic Supplier")
    assert confirmation.status_code==200,confirmation.text
    assert confirmation.json()["status"]=="external_confirmation_reported"
    assert confirmation.json()["provider_booking_independently_verified"] is False
    assert move(client,admin,sid,"cancel","UNSAFE-CANCEL-18").status_code==409
    history=client.get(ROOT+"/stays/"+sid+"/history",headers=admin)
    assert history.status_code==200
    assert len(history.json()["items"])==3
    assert history.json()["supplier_acknowledgment_verified"] is False
    with Session() as db:
        assert db.query(AccommodationProperty).count()==1
        assert db.query(AccommodationStay).count()==1
        assert db.query(AccommodationInventory).count()==1
        assert db.query(AccommodationEvent).count()==3


def test_overlap_capacity_nightly_inventory_guards_and_release(seeded):
    (client,auth,_,_),admin,p,c=seeded
    pid,inventory_id=setup(client,admin,p["id"],rooms=1)
    a=request(client,admin,c["id"],pid,key="HOTEL-ONE-18").json()["id"]
    b=request(client,admin,c["id"],pid,key="HOTEL-TWO-18").json()["id"]
    assert move(client,admin,a,"hold_internally","HOLD-ONE-18").status_code==200
    assert move(client,admin,b,"hold_internally","HOLD-TWO-18").status_code==409
    # Active reservation references prevent deleting their proposed inventory source.
    assert client.post(ROOT+"/inventory/"+inventory_id+"/revoke",headers=admin).status_code==409
    cancel=move(client,admin,a,"cancel","CANCEL-ONE-18")
    assert cancel.status_code==200 and cancel.json()["status"]=="cancelled"
    assert move(client,admin,b,"hold_internally","HOLD-TWO-18").status_code==200
    overlapping=client.post(ROOT+"/properties/"+pid+"/inventory",headers=admin,json={
       "room_type":"double","starts_on":days()[0],"ends_on":days()[1],
       "proposed_rooms":5,"reference":"DOUBLE-COUNT-CAPACITY-18"})
    assert overlapping.status_code==409


def test_non_overlapping_half_open_stays_share_one_room(seeded):
    (client,auth,_,_),admin,p,c=seeded
    pid,inv=setup(client,admin,p["id"],rooms=1)
    first,middle=days(10,2)
    last=days()[1]
    for key,start,end in [("HOTEL-EARLY-18",first,middle),("HOTEL-LATE-18",middle,last)]:
        response=request(client,admin,c["id"],pid,key=key,starts_on=start,ends_on=end)
        assert response.status_code==201,response.text
        h=move(client,admin,response.json()["id"],"hold_internally","HOLD-"+key)
        assert h.status_code==200,h.text


def test_revoked_consent_blocks_current_requests_permanently(seeded):
    (client,auth,_,Session),admin,p,c=seeded
    pid,_=setup(client,admin,p["id"])
    sid=request(client,admin,c["id"],pid).json()["id"]
    assert move(client,admin,sid,"hold_internally","HOLD-BEFORE-WITHDRAW-18").status_code==200
    token=client.post("/api/v1/consent-links/"+p["id"]+"/accommodation_coordination",
       headers=admin).json()["token"]
    revoked=client.post("/api/v1/consent-links/respond",json={
       "token":token,"notice_version":"v18-synthetic","accepted":False})
    assert revoked.status_code==201,revoked.text
    assert client.get(ROOT+"/cases/"+c["id"]+"/stays",headers=admin).status_code==409
    with Session() as db:
        assert db.query(AccommodationStay).filter(AccommodationStay.id==sid).one().status=="blocked"
    allow(client,admin,p["id"])
    listed=client.get(ROOT+"/cases/"+c["id"]+"/stays",headers=admin)
    assert listed.status_code==200 and listed.json()["items"][0]["status"]=="blocked"
    assert request(client,admin,c["id"],pid).status_code==409
    assert move(client,admin,sid,"hold_internally","REOPEN-FAIL-18").status_code==409
    new=request(client,admin,c["id"],pid,key="NEW-AFTER-CONSENT-18")
    assert new.status_code==201 and new.json()["id"]!=sid


def test_intake_withdrawal_blocks_accommodation(seeded):
    (client,auth,_,Session),admin,p,c=seeded
    pid,_=setup(client,admin,p["id"])
    sid=request(client,admin,c["id"],pid).json()["id"]
    res=client.post("/api/v1/consents",headers=admin,json={
       "patient_id":p["id"],"purpose":"intake","accepted":False,"notice_version":"v18-synthetic"})
    assert res.status_code==201
    with Session() as db:
        assert db.query(AccommodationStay).filter(AccommodationStay.id==sid).one().status=="blocked"


def test_tenant_isolation_and_outside_property_rejected(seeded):
    (client,auth,_,_),admin,p,c=seeded
    pid,inv=setup(client,admin,p["id"])
    sid=request(client,admin,c["id"],pid).json()["id"]
    outsider=auth("b")
    assert client.get(ROOT+"/properties",headers=outsider).json()["items"]==[]
    assert client.get(ROOT+"/properties/"+pid+"/inventory",headers=outsider).status_code==404
    assert client.post(ROOT+"/inventory/"+inv+"/revoke",headers=outsider).status_code==404
    assert client.get(ROOT+"/cases/"+c["id"]+"/stays",headers=outsider).status_code==404
    assert client.get(ROOT+"/stays/"+sid+"/history",headers=outsider).status_code==404
    assert move(client,outsider,sid,"hold_internally","FOREIGN-HOLD-18").status_code==404
    assert request(client,outsider,c["id"],pid).status_code==404


def test_forged_fields_invalid_windows_idempotency_and_legacy_bypass(seeded):
    (client,auth,_,_),admin,p,c=seeded
    pid,inv=setup(client,admin,p["id"])
    assert client.post(ROOT+"/properties",headers=admin,json={
       "name":"Synthetic Hotel","city":"Tehran","passport_number":"fake"}).status_code==422
    assert request(client,admin,c["id"],pid,passport_number="sensitive").status_code==422
    assert request(client,admin,c["id"],pid,rooms_requested=2,guests=9).status_code==422
    assert request(client,admin,c["id"],pid,starts_on=days(10,2)[1],
                   ends_on=days(10,2)[0]).status_code==422
    assert request(client,admin,c["id"],pid).status_code==201
    assert request(client,admin,c["id"],pid,rooms_requested=2).status_code==409
    stay=request(client,admin,c["id"],pid,key="OTHER-REQUEST-18").json()["id"]
    assert move(client,admin,stay,"hold_internally","HOLD-REPLAY-18").status_code==200
    assert move(client,admin,stay,"hold_internally","HOLD-REPLAY-18").json()["reused"] is True
    assert client.post(ROOT+"/stays/"+stay+"/transition",headers=admin,json={
       "step_key":"HOLD-REPLAY-18","action":"cancel","reference":"LOCAL-REVIEW-18"}).status_code==409
    travel=client.post("/api/v1/travel",headers=admin,json={
       "case_id":c["id"],"service_type":"hotel","notes":"Synthetic accommodation inquiry"})
    assert travel.status_code==201
    assert client.patch("/api/v1/travel/"+travel.json()["id"]+"/status",headers=admin,json={
        "status":"confirmed","reference":"UNVERIFIED-BOOKING-18"}).status_code==409
    operation=client.post("/api/v1/operations",headers=admin,json={
       "kind":"hotel","case_id":c["id"],"title":"Synthetic vendor coordination"}).json()
    assert client.post("/api/v1/operations/"+operation["id"]+"/transition",
        headers=admin,json={"status":"in_review"}).status_code==200
    assert client.post("/api/v1/operations/"+operation["id"]+"/transition",
        headers=admin,json={"status":"awaiting_external"}).status_code==200
    assert client.post("/api/v1/operations/"+operation["id"]+"/transition",
        headers=admin,json={"status":"confirmed","reference":"UNVERIFIED-BOOKING-18"}).status_code==409


def test_due_and_inventory_revoke_without_active_holds(seeded):
    (client,auth,_,_),admin,p,c=seeded
    pid,inv=setup(client,admin,p["id"])
    original=client.get(ROOT+"/properties/"+pid+"/inventory",headers=admin)
    assert original.status_code==200 and original.json()["actual_capacity_connected"] is False
    assert client.get(ROOT+"/due",headers=auth("b")).json()["items"]==[]
    r=request(client,admin,c["id"],pid)
    assert r.status_code==201
    assert any(x["id"]==r.json()["id"] for x in client.get(ROOT+"/due",headers=admin).json()["items"])
    revoked=client.post(ROOT+"/inventory/"+inv+"/revoke",headers=admin)
    assert revoked.status_code==200 and revoked.json()["status"]=="revoked"
    assert move(client,admin,r.json()["id"],"hold_internally","NO-STOCK-HOLD-18").status_code==409
