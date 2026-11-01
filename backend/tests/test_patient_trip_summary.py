"""The patient sees one trip summary: visa, hotel, airport transfer and readiness (synthetic data)."""
from datetime import date, timedelta, datetime, timezone

from test_enterprise import _patient_token


def consent(client, h, pid, purpose, accepted=True):
    r = client.post("/api/v1/consents", headers=h, json={"patient_id": pid, "purpose": purpose,
                                                           "accepted": accepted, "notice_version": "TEST"})
    assert r.status_code == 201, r.text


def portal(client, admin, pid):
    r = client.post("/api/v1/portal/invites/" + pid, headers=admin)
    assert r.status_code == 201, r.text
    return {"X-Patient-Access": _patient_token(client, r)}


def trip(client, h):
    data = client.get("/api/v1/portal/journey", headers=h).json()
    return data[0]["travel"]


def test_trip_summary_shows_visa_hotel_transfer_and_readiness(seeded):
    (client, auth, _, _), admin, p, c = seeded
    for purpose in ("communication", "visa_coordination", "accommodation_coordination", "transport_coordination"):
        consent(client, admin, p["id"], purpose)
    h = portal(client, admin, p["id"])
    empty = trip(client, h)
    assert empty["visa"] == [] and empty["accommodation"] == [] and empty["transfers"] == []
    assert not empty["readiness"]["ready_to_travel"]
    assert {"appointment", "quote", "accommodation", "case_approval"} <= set(empty["readiness"]["pending"])

    soon = datetime.now(timezone.utc) + timedelta(days=20)
    visa = client.post(f"/api/v1/visa-coordination/cases/{c['id']}/applications", headers=admin,
                       json={"request_key": "TEST-visa-0001", "origin_country": "AF",
                             "intended_departure_at": soon.isoformat()}).json()
    prop = client.post("/api/v1/accommodation/properties", headers=admin,
                       json={"name": "TEST Hotel", "city": "Tehran"}).json()
    start = date.today() + timedelta(days=21)
    stay = client.post(f"/api/v1/accommodation/cases/{c['id']}/stays", headers=admin,
                       json={"request_key": "TEST-stay-0001", "property_id": prop["id"], "room_type": "double",
                             "starts_on": start.isoformat(), "ends_on": (start + timedelta(days=5)).isoformat(),
                             "rooms_requested": 1, "guests": 2})
    assert stay.status_code == 201, stay.text
    seen = trip(client, h)
    assert seen["visa"][0]["status"] == "requested" and not seen["visa"][0]["issued_reported"]
    assert seen["accommodation"][0]["hotel"] == "TEST Hotel" and not seen["accommodation"][0]["confirmed"]
    assert {"visa", "accommodation"} <= set(seen["readiness"]["pending"])
    # Internal references never reach the patient.
    text = str(seen)
    assert "TEST-visa-0001" not in text and "TEST-stay-0001" not in text and visa["id"] not in text

    # The open visa now blocks the travel milestone for staff as well.
    mission = client.get(f"/api/v1/cases/{c['id']}/mission", headers=admin).json()
    assert not mission["conditions"]["travel_resolved"]
    assert mission["signals"]["visa_records_recorded"] == 1


def test_each_trip_part_needs_its_own_consent(seeded):
    (client, auth, _, _), admin, p, c = seeded
    for purpose in ("communication", "visa_coordination", "accommodation_coordination"):
        consent(client, admin, p["id"], purpose)
    h = portal(client, admin, p["id"])
    soon = datetime.now(timezone.utc) + timedelta(days=20)
    assert client.post(f"/api/v1/visa-coordination/cases/{c['id']}/applications", headers=admin,
                       json={"request_key": "TEST-visa-0002", "origin_country": "AF",
                             "intended_departure_at": soon.isoformat()}).status_code == 201
    assert len(trip(client, h)["visa"]) == 1
    consent(client, admin, p["id"], "visa_coordination", accepted=False)
    # Withdrawal ends the current portal session; a fresh session no longer shows the visa part.
    assert client.get("/api/v1/portal/journey", headers=h).status_code == 401
    assert trip(client, portal(client, admin, p["id"]))["visa"] == []


def test_other_tenant_trip_is_not_visible(seeded):
    (client, auth, _, _), admin, p, c = seeded
    consent(client, admin, p["id"], "communication")
    h = portal(client, admin, p["id"])
    data = client.get("/api/v1/portal/journey", headers=h).json()
    assert [x["case_id"] for x in data] == [c["id"]]
