"""Two independent tenants on real PostgreSQL with forced row-level security.

Run with: MEDTOUR_TEST_PG=postgresql+psycopg://OWNER@HOST:PORT/DB pytest tests/test_tenant_rls_isolation.py
The API uses the non-privileged ``medtour_app`` role exactly as in production.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.skipif(not os.environ.get("MEDTOUR_TEST_PG"), reason="requires MEDTOUR_TEST_PG (PostgreSQL)")


def _tenant_data(client, headers, name):
    p = client.post("/api/v1/patients", headers=headers, json={"full_name": name, "language": "fa", "country": "AF",
                                                               "contact": name.lower().replace(" ", "") + "@example.test"}).json()
    for purpose in ("intake", "communication", "medical_documents"):
        assert client.post("/api/v1/consents", headers=headers, json={"patient_id": p["id"], "purpose": purpose,
                                                                      "accepted": True, "notice_version": "v1"}).status_code == 201
    case = client.post("/api/v1/cases", headers=headers, json={"patient_id": p["id"], "complaint": "synthetic", "specialty": "orthopedics"}).json()
    quote = client.post("/api/v1/quotes", headers=headers, json={"case_id": case["id"], "currency": "USD", "amount_minor": 0}).json()
    return p, case, quote


@pytest.fixture()
def two_tenants(context, monkeypatch, tmp_path):
    client, auth, tids, Session = context
    monkeypatch.setenv("ALLOW_DEV_ENCRYPTED_UPLOADS", "true")
    import base64
    monkeypatch.setenv("DOCUMENT_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("PRIVATE_DOCUMENT_DIR", str(tmp_path))
    a, b = auth("a"), auth("b")
    pa, ca, qa = _tenant_data(client, a, "Tenant A Patient")
    pb, cb, qb = _tenant_data(client, b, "Tenant B Patient")
    doc = client.post(f"/api/v1/secure-documents/cases/{ca['id']}", headers=a,
                      files={"file": ("a.pdf", b"%PDF-1.4\ntenant-a", "application/pdf")})
    assert doc.status_code == 201, doc.text
    return client, auth, tids, Session, (a, pa, ca, qa, doc.json()["id"]), (b, pb, cb, qb)


def test_runtime_role_is_non_privileged_and_rls_effective(two_tenants, pg_engines):
    client, auth, tids, Session, A, B = two_tenants
    from app.tenant_rls import runtime_status
    admin, app_engine = pg_engines
    with app_engine.connect() as conn:
        status = runtime_status(conn)
    assert status["runtime_role_nonprivileged"] is True
    assert status["rls_effective"] is True
    assert status["tenant_scoped_tables"] == status["rls_enforced_tables"] >= 37
    resp = client.get("/api/v1/admin/tenant-isolation/status", headers=A[0])
    assert resp.status_code == 200, resp.text
    live = resp.json()
    assert live["runtime_role_nonprivileged"] is True and live["authenticated_tenant_role"] is True


def test_tenant_b_cannot_reach_tenant_a_through_the_api(two_tenants):
    client, auth, tids, Session, (a, pa, ca, qa, doc), (b, pb, cb, qb) = two_tenants
    assert {x["id"] for x in client.get("/api/v1/patients", headers=b).json()} == {pb["id"]}
    assert {x["id"] for x in client.get("/api/v1/cases", headers=b).json()} == {cb["id"]}
    assert {x["id"] for x in client.get("/api/v1/quotes", headers=b).json()} == {qb["id"]}
    assert client.get(f"/api/v1/patients/{pa['id']}", headers=b).status_code == 404
    assert client.get(f"/api/v1/cases/{ca['id']}", headers=b).status_code == 404
    assert client.get(f"/api/v1/secure-documents/cases/{ca['id']}/list", headers=b).status_code == 404
    assert client.get(f"/api/v1/secure-documents/{doc}", headers=b).status_code == 404
    assert client.get(f"/api/v1/secure-documents/{doc}", headers=a).status_code == 200
    assert client.post("/api/v1/cases", headers=b, json={"patient_id": pa["id"], "complaint": "x"}).status_code in (404, 409)
    b_audit = {e["entity_id"] for e in client.get("/api/v1/audit", headers=b).json()}
    assert not b_audit & {pa["id"], ca["id"], doc}
    with Session() as db:  # owner view confirms tenant A's events exist; tenant B just cannot see them
        assert db.execute(text("SELECT count(*) FROM audit_events WHERE entity_id=:d"), {"d": doc}).scalar() >= 1


def test_database_hides_rows_even_when_a_query_forgets_the_tenant_filter(two_tenants, pg_engines):
    """Simulates the application bug RLS exists for: SELECT without WHERE tenant_id."""
    client, auth, tids, Session, A, B = two_tenants
    from app.tenant_context import bind_tenant, system_scope
    from sqlalchemy.orm import sessionmaker
    admin, app_engine = pg_engines
    AppSession = sessionmaker(bind=app_engine)
    ta, tb = tids
    with AppSession() as db:
        assert db.execute(text("SELECT count(*) FROM patients")).scalar() == 0  # nothing bound: nothing visible
        bind_tenant(db, tb)
        names = db.execute(text("SELECT full_name FROM patients")).scalars().all()
        assert names == ["Tenant B Patient"]
        assert db.execute(text("SELECT count(*) FROM documents")).scalar() == 0
        with system_scope(db):
            assert db.execute(text("SELECT count(*) FROM patients")).scalar() == 2
        assert db.execute(text("SELECT count(*) FROM patients")).scalar() == 1
    with AppSession() as db:
        bind_tenant(db, tb)
        with pytest.raises(DBAPIError):  # WITH CHECK: cannot write rows for another tenant
            db.execute(text("INSERT INTO patients (id, tenant_id, full_name, country, language, contact, created_at) "
                            "VALUES ('00000000-0000-4000-8000-0000000000aa', :t, 'Injected', 'AF', 'fa', '', now())"), {"t": ta})
            db.flush()
    with AppSession() as db:
        bind_tenant(db, tb)
        changed = db.execute(text("UPDATE patients SET full_name='hijacked'")).rowcount
        db.commit()
        assert changed == 1
    with Session() as owner:
        assert owner.execute(text("SELECT full_name FROM patients WHERE tenant_id=:a"), {"a": ta}).scalar() == "Tenant A Patient"


def test_context_does_not_leak_between_pooled_transactions(two_tenants, pg_engines):
    client, auth, tids, Session, A, B = two_tenants
    from app.tenant_context import bind_tenant
    from sqlalchemy.orm import sessionmaker
    admin, app_engine = pg_engines
    AppSession = sessionmaker(bind=app_engine)
    with AppSession() as db:
        bind_tenant(db, tids[0])
        assert db.execute(text("SELECT count(*) FROM patients")).scalar() == 1
        db.commit()
    for _ in range(5):  # fresh sessions reuse the same pooled connections
        with AppSession() as db:
            assert db.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar() in ("", None)
            assert db.execute(text("SELECT count(*) FROM patients")).scalar() == 0


def test_patient_portal_and_refresh_resolve_only_their_own_tenant(two_tenants):
    client, auth, tids, Session, (a, pa, ca, qa, doc), (b, pb, cb, qb) = two_tenants
    invite = client.post(f"/api/v1/portal/invites/{pb['id']}", headers=b).json()
    session = client.post("/api/v1/portal/session/exchange", json={"invitation_token": invite["token"],
                                                                   "verification_code": invite["demo_verification_code"]})
    assert session.status_code == 201, session.text
    portal = {"X-Patient-Access": session.json()["access_token"]}
    assert client.get("/api/v1/portal/me", headers=portal).json()["id"] == pb["id"]
    assert client.get(f"/api/v1/secure-documents/portal/cases/{ca['id']}/list", headers=portal).status_code == 404
    login = client.post("/api/v1/auth/login", json={"tenant_slug": "a", "email": "a@example.test", "password": "test_password_12345"}).json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200 and refreshed.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + refreshed.json()["access_token"]}).json()
    assert me["tenant_id"] == tids[0]


def test_appointments_and_quotes_are_isolated(two_tenants):
    client, auth, tids, Session, (a, pa, ca, qa, doc), (b, pb, cb, qb) = two_tenants
    dr = client.post("/api/v1/physicians", headers=a, json={"full_name": "A Doctor", "specialty": "orthopedics"}).json()
    assert client.get("/api/v1/physicians", headers=b).json() == []
    assert client.post(f"/api/v1/quotes/{qa['id']}/items", headers=b, json={"label": "Synthetic item", "units": 1,
                                                                            "unit_amount_minor": 1, "provenance": "TEST"}).status_code == 404
    assert client.get("/api/v1/appointments", headers=b).json() == []
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    assert client.post("/api/v1/appointments", headers=b, json={"case_id": cb["id"], "physician_id": dr["id"],
                                                                "requested_at": when}).status_code == 404
