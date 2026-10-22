"""Synthetic tenant isolation and RBAC checks for read-only audit feed."""
from app.models import User
from app.security import password_hash


def test_audit_feed_is_tenant_scoped_and_paginated(context):
    client, auth, ids, Session = context
    a = auth("a")
    b = auth("b")
    created_a = client.post(
        "/api/v1/patients", headers=a,
        json={"full_name": "Synthetic A", "language": "en"}
    )
    created_b = client.post(
        "/api/v1/patients", headers=b,
        json={"full_name": "Synthetic B", "language": "en"}
    )
    assert created_a.status_code == created_b.status_code == 201
    event_a = client.get("/api/v1/audit-events", headers=a)
    event_b = client.get("/api/v1/audit-events", headers=b)
    assert event_a.status_code == event_b.status_code == 200
    assert len(event_a.json()) == len(event_b.json()) == 1
    assert event_a.json()[0]["entity_id"] == created_a.json()["id"]
    assert event_b.json()[0]["entity_id"] == created_b.json()["id"]
    assert client.get("/api/v1/audit-events?limit=1&offset=1", headers=a).json() == []
    assert client.get("/api/v1/audit-events?limit=0", headers=a).status_code == 422
    assert client.get("/api/v1/audit-events?limit=101", headers=a).status_code == 422


def test_audit_feed_requires_auditor_or_admin(context):
    client, auth, ids, Session = context
    assert client.get("/api/v1/audit-events").status_code == 401
    operator = auth("a", "operator@example.test")
    assert client.get("/api/v1/audit-events", headers=operator).status_code == 403
    with Session() as db:
        db.add(User(
            tenant_id=ids[0], email="auditor@example.test",
            password_hash=password_hash("test_password_12345"), role="auditor"
        ))
        db.commit()
    auditor = auth("a", "auditor@example.test")
    assert client.get("/api/v1/audit-events", headers=auditor).status_code == 200
