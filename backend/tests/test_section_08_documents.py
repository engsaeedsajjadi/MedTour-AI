"""Section 08: synthetic-only medical document security, authorization, integrity."""
import base64
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Audit, Document
from app.enterprise_models import MedicalDocumentEvent
from app.medical_document_policy import cleaned_name, document_path, LOCAL_BLOB_MAX
from app.secure_media import MAX_BYTES

RAW = b"%PDF-1.4\nSYNTHETIC DOCUMENT 08\n%%EOF"


def _config(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_DEV_ENCRYPTED_UPLOADS", "true")
    monkeypatch.setenv("DOCUMENT_ENCRYPTION_KEY",
                       base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("PRIVATE_DOCUMENT_DIR", str(tmp_path))


def _consent(client, headers, patient_id, accepted=True):
    response = client.post("/api/v1/consents", headers=headers, json={
        "patient_id": patient_id, "purpose": "medical_documents",
        "accepted": accepted, "notice_version": "section08",
    })
    assert response.status_code == 201, response.text


def _portal(client, admin, patient_id):
    response = client.post("/api/v1/consents", headers=admin, json={
        "patient_id": patient_id, "purpose": "communication",
        "accepted": True, "notice_version": "section08",
    })
    assert response.status_code == 201
    invite = client.post("/api/v1/portal/invites/" + patient_id, headers=admin)
    assert invite.status_code == 201, invite.text
    return {"X-Patient-Access": invite.json()["token"]}


def _staff_upload(client, admin, case_id, name="synthetic.pdf", raw=RAW):
    return client.post("/api/v1/secure-documents/cases/" + case_id,
                       headers=admin,
                       files={"file": (name, raw, "application/pdf")})


def test_private_staff_upload_and_patient_download_with_no_cache(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, patient, case = seeded
    _config(monkeypatch, tmp_path)
    _consent(client, admin, patient["id"])
    portal = _portal(client, admin, patient["id"])
    result = _staff_upload(client, admin, case["id"], "C:\\medical\\private.pdf")
    assert result.status_code == 201, result.text
    doc_id = result.json()["id"]
    assert result.json()["status"] == "encrypted_dev_unscanned"
    assert result.json()["production_approved"] is False
    assert b"SYNTHETIC DOCUMENT" not in next(tmp_path.rglob("*.enc")).read_bytes()
    readiness = client.get("/api/v1/secure-documents/readiness", headers=admin)
    assert readiness.status_code == 200
    assert readiness.json()["storage_mode"] == "local_encrypted_unscanned_test"
    assert not readiness.json()["actual_s3_kms_scanner_verified"]
    assert client.get("/api/v1/secure-documents/readiness").status_code == 401
    staff_list = client.get(
        f"/api/v1/secure-documents/cases/{case['id']}/list", headers=admin
    )
    assert staff_list.status_code == 200
    assert staff_list.json()[0]["filename"] == "private.pdf"
    assert "storage_key" not in str(staff_list.json())
    staff_download = client.get("/api/v1/secure-documents/" + doc_id, headers=admin)
    assert staff_download.status_code == 200, staff_download.text
    assert staff_download.content == RAW
    assert staff_download.headers["cache-control"] == "no-store, private"
    assert staff_download.headers["x-content-type-options"] == "nosniff"
    assert staff_download.headers["content-security-policy"] == "sandbox"
    patient_download_url = f"/api/v1/secure-documents/portal/cases/{case['id']}/documents/{doc_id}"
    assert client.get(patient_download_url).status_code == 401
    response = client.get(patient_download_url, headers=portal)
    assert response.status_code == 200
    assert response.content == RAW
    with Session() as db:
        audit_events = [x.event for x in db.query(Audit).filter(
            Audit.tenant_id == tids[0], Audit.entity_id == doc_id
        ).all()]
        assert "medical_document_accessed" in audit_events
        portal_events = db.query(MedicalDocumentEvent).filter(
            MedicalDocumentEvent.tenant_id == tids[0],
            MedicalDocumentEvent.document_id == doc_id
        ).all()
        assert len(portal_events) == 1
        assert portal_events[0].actor_type == "portal"
        assert portal_events[0].portal_access_id
        assert portal_events[0].staff_user_id is None
    log = client.get(f"/api/v1/secure-documents/cases/{case['id']}/activity",
                     headers=admin)
    assert log.status_code == 200
    assert log.json()["items"][0]["action"] == "document_downloaded"
    assert "portal_access_id" not in str(log.json())
    assert client.get(f"/api/v1/secure-documents/cases/{case['id']}/activity",
                      headers=auth("b")).status_code == 404


def test_patient_cannot_read_a_different_patient_case_even_same_tenant(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, patient, case = seeded
    _config(monkeypatch, tmp_path)
    _consent(client, admin, patient["id"])
    original = _staff_upload(client, admin, case["id"])
    assert original.status_code == 201
    doc_id = original.json()["id"]
    stranger = client.post("/api/v1/patients", headers=admin,
                           json={"full_name": "Synthetic other patient"}).json()
    _consent(client, admin, stranger["id"])
    alien = _portal(client, admin, stranger["id"])
    url = f"/api/v1/secure-documents/portal/cases/{case['id']}/documents/{doc_id}"
    assert client.get(url, headers=alien).status_code == 404
    assert client.get("/api/v1/secure-documents/" + doc_id, headers=auth("b")).status_code == 404
    assert client.get(f"/api/v1/secure-documents/cases/{case['id']}/list",
                      headers=auth("b")).status_code == 404


def test_withdrawn_document_consent_blocks_metadata_and_old_blob_permanently(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, patient, case = seeded
    _config(monkeypatch, tmp_path)
    _consent(client, admin, patient["id"])
    portal = _portal(client, admin, patient["id"])
    uploaded = _staff_upload(client, admin, case["id"])
    assert uploaded.status_code == 201
    doc_id = uploaded.json()["id"]
    _consent(client, admin, patient["id"], accepted=False)
    with Session() as db:
        doc = db.get(Document, doc_id)
        assert doc.status == "access_revoked"
        assert doc.storage_key == doc_id + ".enc"  # No misleading erasure claim.
    assert client.get(f"/api/v1/secure-documents/cases/{case['id']}/list",
                      headers=admin).status_code == 409
    assert client.get("/api/v1/secure-documents/" + doc_id,
                      headers=admin).status_code == 409
    # Even new purpose consent must never implicitly resurrect a withdrawn blob.
    _consent(client, admin, patient["id"])
    assert client.get(f"/api/v1/secure-documents/cases/{case['id']}/list",
                      headers=admin).json() == []
    assert client.get("/api/v1/secure-documents/" + doc_id,
                      headers=admin).status_code == 404
    newer = _staff_upload(client, admin, case["id"])
    assert newer.status_code == 201
    assert newer.json()["id"] != doc_id


def test_staff_listing_requires_latest_consent_even_without_files(seeded):
    (client, auth, tids, Session), admin, patient, case = seeded
    result = client.get(f"/api/v1/secure-documents/cases/{case['id']}/list",
                        headers=admin)
    assert result.status_code == 409


def test_corrupted_ciphertext_or_document_metadata_fails_closed(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, patient, case = seeded
    _config(monkeypatch, tmp_path)
    _consent(client, admin, patient["id"])
    uploaded = _staff_upload(client, admin, case["id"])
    doc_id = uploaded.json()["id"]
    path = document_path(tids[0], doc_id)
    original = path.read_bytes()
    path.write_bytes(original[:12] + bytes([original[12] ^ 1]) + original[13:])
    response = client.get("/api/v1/secure-documents/" + doc_id, headers=admin)
    assert response.status_code == 500
    assert "SYNTHETIC DOCUMENT" not in response.text
    path.write_bytes(original)
    with Session() as db:
        row = db.get(Document, doc_id)
        row.sha256_hex = "0" * 64
        db.commit()
    assert client.get("/api/v1/secure-documents/" + doc_id,
                      headers=admin).status_code == 500
    path.write_bytes(b"a" * (LOCAL_BLOB_MAX + 1))
    assert client.get("/api/v1/secure-documents/" + doc_id,
                      headers=admin).status_code == 404


def test_filename_and_private_path_reject_attacker_control(monkeypatch, tmp_path):
    assert cleaned_name(r"C:\temp\PHI.pdf") == "PHI.pdf"
    assert cleaned_name("../../private.pdf") == "private.pdf"
    assert cleaned_name("..\r\n") == "document"
    tenant = str(uuid4())
    doc = str(uuid4())
    monkeypatch.setenv("PRIVATE_DOCUMENT_DIR", str(tmp_path))
    assert document_path(tenant, doc).parent == tmp_path / tenant
    with pytest.raises(HTTPException) as exc:
        document_path("../outside", doc)
    assert exc.value.status_code == 422
    outside = tmp_path.parent / "outside-doc-private"
    outside.mkdir(exist_ok=True)
    (tmp_path / tenant).symlink_to(outside, target_is_directory=True)
    with pytest.raises(HTTPException):
        document_path(tenant, doc)


def test_invalid_file_signatures_and_oversize_not_persisted(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, patient, case = seeded
    _config(monkeypatch, tmp_path)
    _consent(client, admin, patient["id"])
    for raw, expected in ((b"", 422), (b"<html>malicious</html>", 415),
                          (b"X" * (MAX_BYTES + 1), 413)):
        result = _staff_upload(client, admin, case["id"], raw=raw)
        assert result.status_code == expected
    with Session() as db:
        assert db.query(Document).count() == 0


def test_patient_upload_writes_portal_actor_metadata_not_invalid_staff_fk(seeded, monkeypatch, tmp_path):
    (client, auth, tids, Session), admin, patient, case = seeded
    _config(monkeypatch, tmp_path)
    _consent(client, admin, patient["id"])
    portal = _portal(client, admin, patient["id"])
    response = client.post(
        "/api/v1/secure-documents/portal/cases/" + case["id"],
        headers=portal, files={"file": ("synthetic.pdf", RAW, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    with Session() as db:
        rows = db.query(MedicalDocumentEvent).filter(
            MedicalDocumentEvent.document_id == response.json()["id"]
        ).all()
        assert len(rows) == 1
        assert rows[0].actor_type == "portal"
        assert rows[0].staff_user_id is None
        assert rows[0].portal_access_id is not None
        assert rows[0].action == "document_uploaded"
        assert db.get(Document, response.json()["id"]).status == "encrypted_dev_unscanned"
