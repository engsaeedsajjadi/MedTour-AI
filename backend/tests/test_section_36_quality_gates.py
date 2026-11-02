"""Section 36 security smoke: synthetic tenant boundary and sensitive response controls."""
import re

def test_public_health_does_not_claim_production(context):
    client, _, _, _ = context
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["production_ready"] is False
    assert "secret" not in live.text.lower()

def test_auth_required_and_basic_security_headers(context):
    client, _, _, _ = context
    for url in ("/api/v1/patients", "/api/v1/cases", "/api/v1/audit"):
        response = client.get(url)
        assert response.status_code in (401, 403), (url,response.status_code,response.text)
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("referrer-policy") == "no-referrer"

def test_cross_tenant_patient_and_case_absent(seeded):
    (client, auth, _, _), admin, patient, case = seeded
    foreign = auth("b")
    own_patient = client.get("/api/v1/patients", headers=admin)
    other_patient = client.get("/api/v1/patients", headers=foreign)
    assert own_patient.status_code == other_patient.status_code == 200
    assert any(item["id"] == patient["id"] for item in own_patient.json())
    assert all(item["id"] != patient["id"] for item in other_patient.json())
    other_cases = client.get("/api/v1/cases", headers=foreign)
    assert other_cases.status_code == 200
    assert all(item["id"] != case["id"] for item in other_cases.json())

def test_invalid_login_does_not_expose_credentials(context):
    client, _, _, _ = context
    secret = "synthetic_do_not_echo_password_123"
    response = client.post("/api/v1/auth/login", json={
        "tenant_slug":"a","email":"a@example.test","password":secret})
    assert response.status_code == 401
    assert secret not in response.text
    assert "password_hash" not in response.text
