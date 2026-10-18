"""Browser CORS regression tests for the patient portal (synthetic data only)."""

def test_patient_portal_custom_header_allowed_in_cors_preflight(context):
    client, _, _, _ = context
    origin = "http://localhost:3000"
    for method, headers in (
        ("GET", "x-patient-access"),
        ("POST", "x-patient-access,content-type"),
    ):
        response = client.options(
            "/api/v1/portal/me" if method == "GET" else "/api/v1/portal/intake/sessions",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": headers,
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["access-control-allow-origin"] == origin
        allowed = response.headers["access-control-allow-headers"].lower()
        assert "x-patient-access" in allowed
        assert "content-type" in allowed

def test_patient_portal_no_credential_is_still_rejected(context):
    client, _, _, _ = context
    response = client.get("/api/v1/portal/me", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 401
