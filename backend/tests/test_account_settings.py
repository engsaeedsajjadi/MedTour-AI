"""Self-service settings: personal profile/sessions for every staff member, organization profile for admins."""
from test_enterprise import _patient_token

ORG = {"display_name": "TEST Clinic", "contact_email": "desk@test-clinic.example", "contact_phone": "+98 21 1234 5678",
       "website": "https://test-clinic.example", "privacy_notice_url": "https://test-clinic.example/privacy",
       "patient_support_hours": "Sat-Thu 9:00-17:00", "default_language": "fa", "enabled_languages": ["fa", "en"],
       "timezone": "Asia/Tehran", "default_currency": "EUR"}


def test_personal_profile_roundtrip_and_validation(context):
    client, auth, _, _ = context
    h = auth("a")
    me = client.get("/api/v1/account/profile", headers=h).json()
    assert me["email"] == "a@example.test" and me["timezone"] == "Asia/Tehran" and me["display_name"] == ""
    r = client.put("/api/v1/account/profile", headers=h, json={"display_name": "  TEST   Admin ", "timezone": "Asia/Kabul"})
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "TEST Admin" and r.json()["timezone"] == "Asia/Kabul"
    assert client.put("/api/v1/account/profile", headers=h, json={"timezone": "Mars/Base"}).status_code == 422
    assert client.put("/api/v1/account/profile", headers=h, json={"display_name": "<script>"}).status_code == 422
    assert client.put("/api/v1/account/profile", headers=h, json={"role": "admin"}).status_code == 422
    # Personal preferences are per user, not shared with colleagues.
    other = auth("a", "operator@example.test")
    assert client.get("/api/v1/account/profile", headers=other).json()["display_name"] == ""


def test_sign_out_other_sessions_keeps_this_browser(context):
    client, auth, _, _ = context
    first = auth("a")
    second = auth("a")
    r = client.post("/api/v1/account/sessions/sign-out-others", headers=second)
    assert r.status_code == 200, r.text
    fresh = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 401
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200
    assert len(client.get("/api/v1/account/profile", headers=fresh).json()["sessions"]) == 1


def test_organization_profile_admin_only_and_validated(context):
    client, auth, _, _ = context
    admin, operator = auth("a"), auth("a", "operator@example.test")
    base = client.get("/api/v1/organization/profile", headers=admin).json()
    assert base["editable"] is True and "integrations" in base
    assert base["integrations"]["telegram"]["mode"] in ("off", "polling_test", "webhook")
    assert "SMTP_PASSWORD" in base["integrations"]["managed_on_server"]
    assert client.put("/api/v1/organization/profile", headers=operator, json=ORG).status_code == 403
    seen = client.get("/api/v1/organization/profile", headers=operator).json()
    assert seen["editable"] is False and "integrations" not in seen
    r = client.put("/api/v1/organization/profile", headers=admin, json=ORG)
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["default_currency"] == "EUR"
    for bad in ({"privacy_notice_url": "http://insecure.example/p"}, {"contact_email": "nope"},
                {"default_language": "ar"}, {"enabled_languages": []}, {"timezone": "Nowhere/City"},
                {"default_currency": "XXX"}, {"secret_key": "x"}):
        assert client.put("/api/v1/organization/profile", headers=admin, json={**ORG, **bad}).status_code == 422, bad
    # Tenant b does not see tenant a's organization profile.
    assert client.get("/api/v1/organization/profile", headers=auth("b")).json()["profile"]["display_name"] != "TEST Clinic"


def test_enabled_languages_apply_to_new_patients(context):
    client, auth, _, _ = context
    admin = auth("a")
    assert client.put("/api/v1/organization/profile", headers=admin, json=ORG).status_code == 200
    assert client.post("/api/v1/patients", headers=admin, json={"full_name": "TEST Patient", "language": "ar"}).status_code == 422
    assert client.post("/api/v1/patients", headers=admin, json={"full_name": "TEST Patient", "language": "en"}).status_code == 201


def test_patient_portal_sees_public_contact_details_only(seeded):
    (client, auth, _, _), admin, p, c = seeded
    assert client.put("/api/v1/organization/profile", headers=admin, json=ORG).status_code == 200
    client.post("/api/v1/consents", headers=admin, json={"patient_id": p["id"], "purpose": "communication",
                                                          "accepted": True, "notice_version": "v1"})
    h = {"X-Patient-Access": _patient_token(client, client.post("/api/v1/portal/invites/" + p["id"], headers=admin))}
    org = client.get("/api/v1/portal/organization", headers=h).json()
    assert org["display_name"] == "TEST Clinic" and org["privacy_notice_url"].endswith("/privacy")
    assert "integrations" not in org and "default_currency" not in org
    assert client.get("/api/v1/portal/organization").status_code == 401
