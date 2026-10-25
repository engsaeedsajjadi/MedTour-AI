"""End-to-end *synthetic* case coordination, not real healthcare acceptance."""
from datetime import datetime, timedelta, timezone


def advance(client, headers, case_id, status, reference=None):
    body = {"status": status}
    if reference:
        body["reference"] = reference
    return client.patch(
        f"/api/v1/cases/{case_id}/status", headers=headers, json=body
    )


def test_case_mission_is_private_and_tenant_scoped(seeded):
    (client, auth, _, _), admin, _, case = seeded
    path = f"/api/v1/cases/{case['id']}/mission"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth("b")).status_code == 404
    assert client.get(path, headers=admin).status_code == 200
    assert client.get(path, headers=admin).json()["conditions"]["intake_consent"]
    assert client.get(path, headers=admin).json()["conditions"]["emergency_clear"]
    assert not client.get(path, headers=admin).json()["conditions"]["quote_approved"]
    assert not client.get(path, headers=admin).json()["conditions"]["appointment_confirmed"]


def test_cannot_skip_clinical_referral_or_pretend_a_booking(seeded):
    (client, auth, _, _), admin, _, case = seeded
    case_id = case["id"]
    assert advance(client, admin, case_id, "intake").status_code == 200
    r = advance(client, admin, case_id, "review_pending")
    assert r.status_code == 409
    assert r.json()["detail"]["missing"] == ["intake_submitted"]


def test_emergency_intake_blocks_case_progression(seeded):
    (client, auth, _, _), admin, _, case = seeded
    case_id = case["id"]
    response = client.post(
        "/api/v1/intake/sessions", headers=admin,
        json={"case_id": case_id, "language": "en"}
    )
    assert response.status_code == 201
    intake_id = response.json()["id"]
    emergency = client.post(
        f"/api/v1/intake/sessions/{intake_id}/answer",
        headers=admin, json={"answer": "I have chest pain"}
    )
    assert emergency.status_code == 200
    assert emergency.json()["emergency_keyword_detected"]
    mission = client.get(f"/api/v1/cases/{case_id}/mission", headers=admin).json()
    assert not mission["conditions"]["emergency_clear"]
    assert mission["signals"]["urgent_intake_detected"]
    assert advance(client, admin, case_id, "intake").status_code == 200
    assert advance(client, admin, case_id, "review_pending").status_code == 409


def test_consent_revocation_invalidates_mission_evidence(seeded):
    (client, auth, _, _), admin, patient, case = seeded
    before = client.get(f"/api/v1/cases/{case['id']}/mission", headers=admin).json()
    assert before["conditions"]["intake_consent"]
    x = client.post(
        "/api/v1/consents", headers=admin,
        json={"patient_id": patient["id"], "purpose": "intake",
              "accepted": False, "notice_version": "v2"}
    )
    assert x.status_code == 201
    after = client.get(f"/api/v1/cases/{case['id']}/mission", headers=admin).json()
    assert not after["conditions"]["intake_consent"]


def test_full_synthetic_case_lifecycle_requires_human_evidence(seeded):
    (client, auth, _, _), admin, patient, case = seeded
    case_id = case["id"]
    operator = auth("a", "operator@example.test")
    assert advance(client, admin, case_id, "intake").status_code == 200
    intake = client.post(
        "/api/v1/intake/sessions", headers=admin,
        json={"case_id": case_id, "language": "en"}
    )
    assert intake.status_code == 201
    for _ in range(5):
        answer = client.post(
            f"/api/v1/intake/sessions/{intake.json()['id']}/answer",
            headers=admin, json={"answer": "Routine consultation planning"}
        )
        assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "awaiting_clinician_review"
    for status in ("review_pending", "provider_review"):
        response = advance(client, admin, case_id, status)
        assert response.status_code == 200, response.text
    # A verified doctor alone is not enough to authorize matching.
    dr = client.post(
        "/api/v1/physicians", headers=admin,
        json={"full_name": "Synthetic Physician", "specialty": "cardiology"}
    ).json()
    assert advance(client, admin, case_id, "quote_pending").status_code == 409
    assert client.patch(
        f"/api/v1/physicians/{dr['id']}/verification",
        headers=admin, json={"status": "verified"}
    ).status_code == 200
    referral = client.post(
        "/api/v1/referrals", headers=admin,
        json={"case_id": case_id, "physician_id": dr["id"]}
    ).json()
    assert client.patch(
        f"/api/v1/referrals/{referral['id']}/status",
        headers=admin, json={"status": "approved"}
    ).status_code == 200
    assert advance(client, admin, case_id, "quote_pending").status_code == 200
    assert advance(client, admin, case_id, "quote_sent").status_code == 409
    quote = client.post(
        "/api/v1/quotes", headers=admin,
        json={"case_id": case_id, "currency": "USD", "amount_minor": 25000}
    ).json()
    assert client.patch(
        f"/api/v1/quotes/{quote['id']}/approve", headers=admin
    ).status_code == 200
    assert advance(client, admin, case_id, "quote_sent").status_code == 200
    assert advance(client, admin, case_id, "confirmed", "SYNTHETIC-00001").status_code == 409
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    appointment = client.post(
        "/api/v1/appointments", headers=admin,
        json={"case_id": case_id, "physician_id": dr["id"],
              "requested_at": future}
    ).json()
    assert client.patch(
        f"/api/v1/appointments/{appointment['id']}/status",
        headers=admin,
        json={"status": "confirmed", "reference": "SYNTHETIC-APPT"}
    ).status_code == 200
    assert advance(client, operator, case_id, "confirmed", "SYNTHETIC-00001").status_code == 403
    assert advance(client, admin, case_id, "confirmed").status_code == 422
    assert advance(client, admin, case_id, "confirmed", "SYNTHETIC-00001").status_code == 200
    assert advance(client, admin, case_id, "travel_planning").status_code == 200

    # Recorded travel request must be externally confirmed or cancelled.
    travel = client.post(
        "/api/v1/travel", headers=admin,
        json={"case_id": case_id, "service_type": "hotel"}
    ).json()
    assert advance(client, admin, case_id, "arrived", "SYNTHETIC-ARRIVAL").status_code == 409
    # The legacy shortcut cannot claim a booked hotel.
    assert client.patch(
        f"/api/v1/travel/{travel['id']}/status", headers=admin,
        json={"status": "confirmed", "reference": "SYNTHETIC-HOTEL"}
    ).status_code == 409
    assert client.patch(
        f"/api/v1/travel/{travel['id']}/status", headers=admin,
        json={"status": "cancelled"}
    ).status_code == 200
    assert client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient["id"], "purpose": "accommodation_coordination",
        "accepted": True, "notice_version": "v18-synthetic"}).status_code == 201
    hotel = client.post("/api/v1/accommodation/properties", headers=admin,
       json={"name": "Synthetic Recovery Hotel", "city": "Tehran"})
    assert hotel.status_code == 201, hotel.text
    pid = hotel.json()["id"]
    start = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
    capacity = client.post(f"/api/v1/accommodation/properties/{pid}/inventory",
       headers=admin, json={"room_type": "double", "starts_on": start,
       "ends_on": end, "proposed_rooms": 1, "reference": "LOCAL-STOCK-18"})
    assert capacity.status_code == 201, capacity.text
    stay = client.post(f"/api/v1/accommodation/cases/{case_id}/stays",
       headers=admin, json={"request_key": "STAY-MISSION-18",
       "property_id": pid, "room_type": "double", "starts_on": start,
       "ends_on": end, "rooms_requested": 1, "guests": 2})
    assert stay.status_code == 201, stay.text
    sid = stay.json()["id"]
    assert advance(client, admin, case_id, "arrived", "SYNTHETIC-ARRIVAL").status_code == 409
    for action, key, supplier in (
        ("hold_internally", "HOLD-MISSION-18", None),
        ("report_provider_request", "REQUEST-MISSION-18", "Synthetic Supplier"),
        ("report_provider_confirmation", "RESPONSE-MISSION-18", "Synthetic Supplier"),
    ):
        payload = {"step_key": key, "action": action, "reference": "LOCAL-STAY-18"}
        if supplier:
            payload["supplier_name"] = supplier
        result = client.post(f"/api/v1/accommodation/stays/{sid}/transition",
            headers=admin, json=payload)
        assert result.status_code == 200, result.text
    assert result.json()["provider_booking_independently_verified"] is False
    assert advance(client, admin, case_id, "arrived", "SYNTHETIC-ARRIVAL").status_code == 200
    assert advance(client, admin, case_id, "in_treatment", "SYNTHETIC-CARE").status_code == 200
    assert advance(client, admin, case_id, "follow_up", "SYNTHETIC-FOLLOW").status_code == 200
    assert advance(client, admin, case_id, "closed", "SYNTHETIC-CLOSE").status_code == 409
    op = client.post(
        "/api/v1/operations", headers=admin,
        json={"kind": "followup", "case_id": case_id,
              "title": "Synthetic follow-up approval"}
    ).json()
    for status, ref in (
        ("in_review", None),
        ("awaiting_external", None),
        ("confirmed", "SYNTHETIC-REVIEW"),
    ):
        payload = {"status": status}
        if ref:
            payload["reference"] = ref
        check = client.post(
            f"/api/v1/operations/{op['id']}/transition",
            headers=admin, json=payload
        )
        assert check.status_code == 200, check.text
    assert advance(client, admin, case_id, "closed", "SYNTHETIC-CLOSE").status_code == 200
    history = client.get(f"/api/v1/cases/{case_id}/mission/history", headers=admin)
    assert history.status_code == 200
    assert history.json()[-1]["current_status"] == "closed"
    assert len(history.json()) == 11
    assert client.get(f"/api/v1/cases/{case_id}/mission/history",headers=auth("b")).status_code == 404
