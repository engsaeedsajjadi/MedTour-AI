"""Section 15 synthetic calendar conflict and role regressions."""
from datetime import datetime,timedelta,timezone
from app.enterprise_models import AppointmentSlot
ROOT="/api/v1/appointment-calendar"

def setup(client,admin):
    doctor=client.post("/api/v1/physicians",headers=admin,json={"full_name":"Synthetic Calendar Doctor","specialty":"cardiology"}).json()
    pid=doctor["id"]
    ev=client.put(f"/api/v1/physician-management/physicians/{pid}/credential",headers=admin,json={
        "issuing_country":"IR","issuing_authority":"Synthetic review unit",
        "license_reference":"SYNTH-CALENDAR-15",
        "expires_at":(datetime.now(timezone.utc)+timedelta(days=100)).isoformat()})
    assert ev.status_code==200,ev.text
    start=datetime.now(timezone.utc)+timedelta(days=7)
    slot=client.post(f"/api/v1/physician-management/physicians/{pid}/availability",headers=admin,json={
        "starts_at":start.isoformat(),"ends_at":(start+timedelta(hours=4)).isoformat()})
    assert slot.status_code==201,slot.text
    return pid,start

def make(client,headers,case_id,pid,start,key="CALENDAR-KEY-15",minutes=60):
    return client.post(ROOT+"/requests",headers=headers,json={
        "case_id":case_id,"physician_id":pid,
        "starts_at":start.isoformat(),
        "ends_at":(start+timedelta(minutes=minutes)).isoformat(),
        "request_key":key})

def test_conflict_idempotency_and_manual_confirmation(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid,when=setup(client,admin)
    first=make(client,admin,c["id"],pid,when)
    assert first.status_code==201,first.text
    assert first.json()["external_booking_confirmed"] is False
    idem=make(client,admin,c["id"],pid,when)
    assert idem.status_code==201 and idem.json()["reused"]
    assert make(client,admin,c["id"],pid,when+timedelta(minutes=30),key="OTHER-CALENDAR-15").status_code==409
    review=ROOT+"/requests/"+first.json()["id"]+"/review"
    assert client.post(review,headers=auth("a","operator@example.test"),json={
        "action":"internally_confirmed","reference":"INTERNAL-REVIEW-15"}).status_code==403
    approved=client.post(review,headers=admin,json={"action":"internally_confirmed","reference":"INTERNAL-REVIEW-15"})
    assert approved.status_code==200,approved.text
    assert approved.json()["external_booking_confirmed"] is False
    assert client.post(review,headers=admin,json={"action":"cancelled","reference":"SECOND-REVIEW-15"}).status_code==409
    assert client.patch("/api/v1/appointments/"+first.json()["id"]+"/status",headers=admin,
        json={"status":"confirmed","reference":"LEGACY-BYPASS-15"}).status_code==409
    with Session() as db:assert db.query(AppointmentSlot).count()==1

def test_cancel_releases_slot_and_tenant_isolation(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid,when=setup(client,admin)
    first=make(client,admin,c["id"],pid,when).json()
    assert client.get(ROOT+f"/cases/{c['id']}",headers=auth("b")).status_code==404
    assert make(client,auth("b"),c["id"],pid,when).status_code==404
    cancelled=client.post(ROOT+"/requests/"+first["id"]+"/review",headers=admin,
        json={"action":"cancelled","reference":"CANCEL-REVIEW-15"})
    assert cancelled.status_code==200
    assert make(client,admin,c["id"],pid,when,key="NEW-REQUEST-15").status_code==201

def test_requires_valid_availability_and_timezone(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid,when=setup(client,admin)
    assert make(client,admin,c["id"],pid,when-timedelta(hours=2)).status_code==409
    bad=client.post(ROOT+"/requests",headers=admin,json={
        "case_id":c["id"],"physician_id":pid,
        "starts_at":when.replace(tzinfo=None).isoformat(),
        "ends_at":(when+timedelta(hours=1)).isoformat(),
        "request_key":"BAD-TIMEZONE-15"})
    assert bad.status_code==422
    assert make(client,admin,c["id"],pid,when,minutes=300).status_code==422

def test_withdrawn_intake_consent_rejects_request(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid,when=setup(client,admin)
    result=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":False,"notice_version":"calendar-v15"})
    assert result.status_code==201
    assert make(client,admin,c["id"],pid,when).status_code==409

def test_consent_withdrawal_blocks_previous_calendar_allocations(seeded):
    (client,auth,tids,Session),admin,p,c=seeded
    pid,when=setup(client,admin)
    first=make(client,admin,c["id"],pid,when)
    assert first.status_code==201
    booking_id=first.json()["id"]
    withdrawn=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":False,
        "notice_version":"calendar-15-withdrawal"})
    assert withdrawn.status_code==201
    with Session() as db:
        row=db.query(AppointmentSlot).filter(AppointmentSlot.appointment_id==booking_id).one()
        assert row.status=="blocked"
    consent=client.post("/api/v1/consents",headers=admin,json={
        "patient_id":p["id"],"purpose":"intake","accepted":True,
        "notice_version":"calendar-15-renewal"})
    assert consent.status_code==201
    assert client.get(ROOT+f"/cases/{c['id']}",headers=admin).json()["items"][0]["status"]=="blocked"
    assert client.post(ROOT+f"/requests/{booking_id}/review",headers=admin,
        json={"action":"internally_confirmed","reference":"REVIEW-AFTER-15"}).status_code==409
