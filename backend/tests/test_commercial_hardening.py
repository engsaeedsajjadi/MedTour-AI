"""Commercial-readiness hardening: audit of denied access/logins, appointment cancellation,
document retention and erasure, staff MFA enforcement, OTP delivery and the real-patient gate."""
import base64
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException

from app.enterprise_models import AppointmentSlot
from app.models import Appointment, Audit, Document

ROOT = "/api/v1/appointment-calendar"


def _events(Session, event):
    with Session() as db:
        return db.query(Audit).filter(Audit.event == event).all()


# --- 3. audit ---------------------------------------------------------------

def test_denied_access_is_audited_with_route_and_role(seeded):
    (client, auth, tids, Session), admin, p, c = seeded
    operator = auth("a", "operator@example.test")
    assert client.get("/api/v1/staff", headers=operator).status_code == 403
    rows = _events(Session, "access_denied")
    assert len(rows) == 1
    assert rows[0].tenant_id == tids[0]
    assert rows[0].detail == "GET /api/v1/staff role=operator"


def test_login_success_and_failure_are_audited_without_secrets(context):
    client, auth, tids, Session = context
    bad = client.post("/api/v1/auth/login", json={"tenant_slug": "a", "email": "a@example.test", "password": "wrong-password-123"})
    assert bad.status_code == 401
    unknown = client.post("/api/v1/auth/login", json={"tenant_slug": "a", "email": "ghost@example.test", "password": "wrong-password-123"})
    assert unknown.status_code == 401
    auth("a")
    failed = _events(Session, "staff_login_failed")
    assert len(failed) == 2
    assert all("password" not in (r.detail or "") for r in failed)
    assert any(r.entity_id.startswith("sha256:") for r in failed)
    assert len(_events(Session, "staff_login_succeeded")) == 1


# --- 6. appointments --------------------------------------------------------

def _calendar(client, admin, case_id):
    doctor = client.post("/api/v1/physicians", headers=admin, json={"full_name": "Synthetic Hardening Doctor", "specialty": "cardiology"}).json()
    pid = doctor["id"]
    assert client.put(f"/api/v1/physician-management/physicians/{pid}/credential", headers=admin, json={
        "issuing_country": "IR", "issuing_authority": "Synthetic review unit", "license_reference": "SYNTH-HARDEN-1",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=100)).isoformat()}).status_code == 200
    start = datetime.now(timezone.utc) + timedelta(days=9)
    slot = client.post(f"/api/v1/physician-management/physicians/{pid}/availability", headers=admin, json={
        "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=3)).isoformat()})
    assert slot.status_code == 201, slot.text

    def book(offset, key):
        r = client.post(ROOT + "/requests", headers=admin, json={
            "case_id": case_id, "physician_id": pid, "starts_at": (start + timedelta(hours=offset)).isoformat(),
            "ends_at": (start + timedelta(hours=offset, minutes=60)).isoformat(), "request_key": key})
        assert r.status_code == 201, r.text
        return r.json()["id"]
    return pid, start, slot.json()["id"], book


def test_confirmed_appointment_can_be_cancelled_and_frees_the_slot(seeded):
    (client, auth, tids, Session), admin, p, c = seeded
    pid, start, availability, book = _calendar(client, admin, c["id"])
    first = book(0, "HARDEN-KEY-0001")
    review = ROOT + f"/requests/{first}/review"
    assert client.post(review, headers=admin, json={"action": "internally_confirmed", "reference": "HARDEN-CONFIRM-1"}).status_code == 200
    with Session() as db:
        assert db.get(Appointment, first).status == "internally_confirmed"
    cancelled = client.post(review, headers=admin, json={"action": "cancelled", "reference": "HARDEN-CANCEL-1"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    with Session() as db:
        assert db.get(Appointment, first).status == "cancelled"
    book(0, "HARDEN-KEY-0002")  # same window is bookable again


def test_cancelling_capacity_requires_handling_its_appointments(seeded):
    (client, auth, tids, Session), admin, p, c = seeded
    pid, start, availability, book = _calendar(client, admin, c["id"])
    pending = book(0, "HARDEN-KEY-0101")
    confirmed = book(1, "HARDEN-KEY-0102")
    assert client.post(ROOT + f"/requests/{confirmed}/review", headers=admin,
                       json={"action": "internally_confirmed", "reference": "HARDEN-CONFIRM-2"}).status_code == 200
    url = f"/api/v1/physician-management/availability/{availability}/cancel"
    refused = client.post(url, headers=admin)
    assert refused.status_code == 409 and "2 active" in refused.json()["detail"]
    cascade = client.post(url + "?cancel_appointments=true", headers=admin)
    assert cascade.status_code == 200 and cascade.json()["cancelled_appointments"] == 2
    with Session() as db:
        statuses = {s.appointment_id: s.status for s in db.query(AppointmentSlot).all()}
    assert statuses == {pending: "cancelled", confirmed: "cancelled"}


def test_pending_request_cannot_be_confirmed_after_capacity_is_withdrawn(seeded):
    (client, auth, tids, Session), admin, p, c = seeded
    pid, start, availability, book = _calendar(client, admin, c["id"])
    pending = book(0, "HARDEN-KEY-0201")
    with Session() as db:
        from app.enterprise_models import PhysicianAvailability
        db.get(PhysicianAvailability, availability).status = "cancelled"
        db.commit()
    late = client.post(ROOT + f"/requests/{pending}/review", headers=admin,
                       json={"action": "internally_confirmed", "reference": "HARDEN-CONFIRM-3"})
    assert late.status_code == 409 and late.json()["detail"] == "Proposed availability is no longer active"


def test_legacy_booking_cannot_double_book_a_physician(seeded):
    (client, auth, tids, Session), admin, p, c = seeded
    dr = client.post("/api/v1/physicians", headers=admin, json={"full_name": "Legacy Doctor", "specialty": "cardiology"}).json()
    client.patch("/api/v1/physicians/" + dr["id"] + "/verification", headers=admin, json={"status": "verified"})
    when = datetime.now(timezone.utc) + timedelta(days=5)
    ok = client.post("/api/v1/appointments", headers=admin, json={"case_id": c["id"], "physician_id": dr["id"], "requested_at": when.isoformat()})
    assert ok.status_code == 201, ok.text
    clash = client.post("/api/v1/appointments", headers=admin, json={"case_id": c["id"], "physician_id": dr["id"],
                                                                      "requested_at": (when + timedelta(minutes=30)).isoformat()})
    assert clash.status_code == 409


# --- 4. storage, retention, erasure ----------------------------------------

def _grant_documents(client, admin, patient_id):
    assert client.post("/api/v1/consents", headers=admin, json={"patient_id": patient_id, "purpose": "medical_documents",
                                                                "accepted": True, "notice_version": "v1"}).status_code == 201


def test_revoked_document_can_be_cryptographically_erased_unless_on_legal_hold(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, p, c = seeded
    monkeypatch.setenv("ALLOW_DEV_ENCRYPTED_UPLOADS", "true")
    monkeypatch.setenv("DOCUMENT_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("PRIVATE_DOCUMENT_DIR", str(tmp_path))
    _grant_documents(client, admin, p["id"])
    up = client.post(f"/api/v1/secure-documents/cases/{c['id']}", headers=admin,
                     files={"file": ("lab.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")})
    assert up.status_code == 201, up.text
    doc = up.json()["id"]
    erase = f"/api/v1/secure-documents/{doc}/erase"
    assert client.post(erase, headers=admin, json={"reference": "ERASE-REQ-001"}).status_code == 409  # still active
    assert client.post(f"/api/v1/secure-documents/{doc}/legal-hold", headers=admin,
                       json={"reference": "HOLD-REQ-001", "legal_hold": True}).status_code == 200
    assert client.post("/api/v1/consents", headers=admin, json={"patient_id": p["id"], "purpose": "medical_documents",
                                                                "accepted": False, "notice_version": "v1"}).status_code == 201
    review = client.get(f"/api/v1/secure-documents/cases/{c['id']}/retention-review", headers=admin).json()
    assert review["documents"][0]["legal_hold"] is True and review["documents"][0]["erasure_due"] is False
    assert client.post(erase, headers=admin, json={"reference": "ERASE-REQ-002"}).status_code == 409
    client.post(f"/api/v1/secure-documents/{doc}/legal-hold", headers=admin, json={"reference": "HOLD-REQ-002", "legal_hold": False})
    done = client.post(erase, headers=admin, json={"reference": "ERASE-REQ-003"})
    assert done.status_code == 200 and done.json()["erased"] is True
    assert not any(tmp_path.rglob("*.enc"))
    with Session() as db:
        row = db.get(Document, doc)
        assert row.status == "erased" and row.storage_key is None and row.erased_at is not None
    assert client.post(erase, headers=admin, json={"reference": "ERASE-REQ-004"}).json()["erased"] is True
    assert len(_events(Session, "medical_document_erased")) == 1
    operator = auth("a", "operator@example.test")
    assert client.post(erase, headers=operator, json={"reference": "ERASE-REQ-005"}).status_code == 403


def test_self_hosted_storage_uses_envelope_encryption(monkeypatch):
    from app import secure_media
    saved = {}

    class FakeS3:
        def put_object(self, **kw): saved.update(kw)
        def get_object(self, **kw): return {"Body": BytesIO(saved["Body"])}
        def delete_object(self, **kw): saved["deleted"] = kw["Key"]

    monkeypatch.setenv("MEDICAL_STORAGE_SELF_HOSTED", "true")
    monkeypatch.setenv("MEDICAL_S3_ENCRYPTION", "client")
    monkeypatch.setenv("MEDICAL_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("MEDICAL_S3_BUCKET", "medtour-medical")
    monkeypatch.setenv("CLAMAV_HOST", "clamav")
    monkeypatch.setenv("DOCUMENT_PROCESSING_APPROVED", "true")
    monkeypatch.setattr(secure_media, "s3_client", lambda: FakeS3())
    assert secure_media.s3_ready()
    tenant, doc = str(uuid.uuid4()), str(uuid.uuid4())
    content = b"%PDF-1.4\nsynthetic envelope"
    mime, digest = secure_media.validate_file(content)
    key, wrapped = secure_media.s3_store_encrypted(tenant, doc, content, mime)
    assert content not in saved["Body"]  # storage only ever sees ciphertext
    assert secure_media.s3_load_encrypted(key, tenant, doc, digest, wrapped) == content
    with pytest.raises(HTTPException):  # bound to its own tenant/document
        secure_media.s3_load_encrypted(key, str(uuid.uuid4()), doc, digest, wrapped)
    with pytest.raises(HTTPException) as erased:  # no wrapped key = cryptographically erased
        secure_media.s3_load_encrypted(key, tenant, doc, digest, None)
    assert erased.value.status_code == 404
    monkeypatch.setenv("MEDICAL_MASTER_KEY", "short")
    assert not secure_media.s3_ready()


# --- 5. MFA and OTP delivery ------------------------------------------------

def test_required_staff_mfa_blocks_password_only_sessions(context, monkeypatch):
    client, auth, tids, Session = context
    headers = auth("a")
    monkeypatch.setenv("STAFF_MFA_REQUIRED", "true")
    assert client.get("/api/v1/patients", headers=headers).json()["detail"] == "Two-factor authentication required"
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/mfa/status", headers=headers).status_code == 200
    monkeypatch.delenv("STAFF_MFA_REQUIRED")
    assert client.get("/api/v1/patients", headers=headers).status_code == 200


def test_portal_invitation_is_delivered_to_patient_not_shown_to_staff(context, monkeypatch):
    client, auth, tids, Session = context
    admin = auth("a")
    p = client.post("/api/v1/patients", headers=admin, json={"full_name": "Synthetic Patient", "language": "fa",
                                                             "country": "AF", "contact": "patient@example.test"}).json()
    for purpose in ("intake", "communication"):
        assert client.post("/api/v1/consents", headers=admin, json={"patient_id": p["id"], "purpose": purpose,
                                                                    "accepted": True, "notice_version": "v1"}).status_code == 201
    sent = {}
    from app import otp_delivery
    monkeypatch.setenv("OTP_DELIVERY_PROVIDER", "email")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setattr(otp_delivery, "_send_email", lambda to, subject, body: sent.update(to=to, body=body))
    r = client.post(f"/api/v1/portal/invites/{p['id']}", headers=admin)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["delivered"] is True and body["channel"] == "email"
    assert "token" not in body and "demo_verification_code" not in body
    assert body["masked_contact"] == "p***@example.test"
    assert sent["to"] == "patient@example.test" and "#invite=" in sent["body"]
    code = [w for w in sent["body"].split() if w.isdigit() and len(w) == 6][0]
    token = sent["body"].split("#invite=")[1].split()[0]
    login = client.post("/api/v1/portal/session/exchange", json={"invitation_token": token, "verification_code": code})
    assert login.status_code == 201, login.text


def test_wrong_portal_code_is_audited(context):
    client, auth, tids, Session = context
    admin = auth("a")
    p = client.post("/api/v1/patients", headers=admin, json={"full_name": "Synthetic Patient", "language": "fa", "country": "AF"}).json()
    for purpose in ("intake", "communication"):
        client.post("/api/v1/consents", headers=admin, json={"patient_id": p["id"], "purpose": purpose, "accepted": True, "notice_version": "v1"})
    invite = client.post(f"/api/v1/portal/invites/{p['id']}", headers=admin).json()
    wrong = "000000" if invite["demo_verification_code"] != "000000" else "111111"
    assert client.post("/api/v1/portal/session/exchange", json={"invitation_token": invite["token"], "verification_code": wrong}).status_code == 401
    assert len(_events(Session, "patient_portal_login_failed")) == 1


# --- 7. real-patient gate ---------------------------------------------------

def test_real_patient_mode_refuses_to_start_without_controls(context, monkeypatch):
    client, auth, tids, Session = context
    from app.compliance import enforce_real_patient_mode
    enforce_real_patient_mode()  # off by default
    monkeypatch.setenv("REAL_PATIENT_DATA_MODE", "true")
    with pytest.raises(RuntimeError) as refused:
        enforce_real_patient_mode()
    assert "privacy_notice" in str(refused.value) and "tenant_isolation" in str(refused.value)
    report = client.get("/api/v1/compliance/readiness", headers=auth("a")).json()
    assert report["ready_for_real_patients"] is False
    assert {c["kind"] for c in report["checks"]} == {"technical", "legal", "review"}
    assert "release_approval" in str(refused.value)
    assert client.get("/api/v1/compliance/readiness", headers=auth("a", "operator@example.test")).status_code == 403


def test_staff_mfa_applies_to_admin_and_operator_only(context, monkeypatch):
    client, auth, tids, Session = context
    monkeypatch.setenv("STAFF_MFA_REQUIRED", "true")
    monkeypatch.delenv("STAFF_MFA_ROLES", raising=False)
    from app.security import staff_mfa_required
    assert staff_mfa_required("admin") and staff_mfa_required("operator")
    assert not staff_mfa_required("hospital") and not staff_mfa_required("physician")
    blocked = client.get("/api/v1/patients", headers=auth("a", "operator@example.test"))
    assert blocked.status_code == 403 and blocked.json()["detail"] == "Two-factor authentication required"
    monkeypatch.setenv("STAFF_MFA_ROLES", "admin")
    assert client.get("/api/v1/patients", headers=auth("a", "operator@example.test")).status_code == 200
    monkeypatch.setenv("APP_ENV", "production")
    assert staff_mfa_required("operator")  # production cannot drop privileged roles
    monkeypatch.setenv("APP_ENV", "test")


def _fake_clamd(reply: bytes):
    import socket, threading
    server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1)
    received = {}
    def serve():
        conn, _ = server.accept()
        data = b""
        while not data.endswith(b"\x00\x00\x00\x00"):
            chunk = conn.recv(65536)
            if not chunk: break
            data += chunk
        received["data"] = data
        conn.sendall(reply); conn.close(); server.close()
    threading.Thread(target=serve, daemon=True).start()
    return server.getsockname()[1], received


@pytest.mark.parametrize("reply,status", [
    (b"stream: Eicar-Signature FOUND\x00", 422),
    (b"garbage\x00", 503),
])
def test_clamav_rejects_infected_or_inconclusive_files(monkeypatch, reply, status):
    from app import secure_media
    port, _ = _fake_clamd(reply)
    monkeypatch.setenv("CLAMAV_HOST", "127.0.0.1"); monkeypatch.setenv("CLAMAV_PORT", str(port))
    with pytest.raises(HTTPException) as rejected:
        secure_media.scan_clamav(b"%PDF-1.4 synthetic")
    assert rejected.value.status_code == status


def test_clamav_clean_file_passes_and_streams_whole_content(monkeypatch):
    from app import secure_media
    port, received = _fake_clamd(b"stream: OK\x00")
    monkeypatch.setenv("CLAMAV_HOST", "127.0.0.1"); monkeypatch.setenv("CLAMAV_PORT", str(port))
    payload = b"%PDF-1.4 " + b"x" * 150_000
    secure_media.scan_clamav(payload)
    assert received["data"].startswith(b"zINSTREAM\x00") and payload[-1000:] in received["data"]


def test_production_is_held_to_full_checklist_even_without_flag(monkeypatch):
    from app.compliance import enforce_real_patient_mode
    monkeypatch.delenv("REAL_PATIENT_DATA_MODE", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    try:
        with pytest.raises(RuntimeError, match="release_approval"):
            enforce_real_patient_mode()
    finally:
        monkeypatch.setenv("APP_ENV", "test")


def test_provision_tenant_creates_isolated_org_and_admin(context, monkeypatch):
    client, auth, tids, Session = context
    from app import provision_tenant
    monkeypatch.setattr(provision_tenant, "SessionLocal", Session)
    for bad in (("Bad Slug", "Org", "a@b.example", "Strong-Password-2026"),
                ("clinic-x", "Org", "not-an-email", "Strong-Password-2026"),
                ("clinic-x", "Org", "a@b.example", "short")):
        with pytest.raises(ValueError):
            provision_tenant.provision(*bad)
    provision_tenant.provision("clinic-x", "Clinic X", "Admin@Clinic-X.example", "Strong-Password-2026")
    with pytest.raises(ValueError, match="already has users"):
        provision_tenant.provision("clinic-x", "Clinic X", "second@clinic-x.example", "Strong-Password-2026")
    login = client.post("/api/v1/auth/login", json={"tenant_slug": "clinic-x", "email": "admin@clinic-x.example",
                                                   "password": "Strong-Password-2026"})
    assert login.status_code == 200 and login.json()["role"] == "admin"
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/v1/patients", headers=headers).json() == []  # sees nothing from tenants a/b
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("Strong-Password-2026\n"))
    assert provision_tenant.main(["--slug", "Bad Slug", "--name", "X", "--admin-email", "x@y.example", "--password-stdin"]) == 2


def test_malware_rejection_is_audited_without_content(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app import document_storage

    def detect(raw):
        raise HTTPException(422, "Malware detected; file rejected")
    monkeypatch.setattr(document_storage, "scan_clamav", detect)

    class DB:
        def __init__(self): self.rows, self.commits = [], 0
        def add(self, row): self.rows.append(row)
        def commit(self): self.commits += 1
    db = DB()
    with pytest.raises(HTTPException) as caught:
        document_storage.scan_or_reject(db, "t-1", "u-1", "c-1", b"%PDF-1.4 TEST", "application/pdf")
    assert caught.value.status_code == 422
    assert db.commits == 1 and db.rows[0].event == "document_malware_rejected"
    assert db.rows[0].tenant_id == "t-1" and "TEST" not in (db.rows[0].detail or "")


def test_scanner_outage_is_not_logged_as_malware(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app import document_storage

    def down(raw):
        raise HTTPException(503, "Malware scanner unavailable; upload denied")
    monkeypatch.setattr(document_storage, "scan_clamav", down)

    class DB:
        rows = []
        def add(self, row): self.rows.append(row)
        def commit(self): pass
    with pytest.raises(HTTPException):
        document_storage.scan_or_reject(DB(), "t", "u", "c", b"x", "application/pdf")
    assert DB.rows == []


def test_provisioned_admin_password_matches_staff_minimum():
    import pytest
    from app.provision_tenant import validate_password
    with pytest.raises(ValueError):
        validate_password("Short-Pass-2026")  # 15 characters
    validate_password("Strong-Password-2026")
