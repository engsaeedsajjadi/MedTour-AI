"""Stage 19.20: real FastAPI request-bound tenant DB routing, synthetic clone only.

Unlike 19.16 this uses ONE shared TestClient that selects the tenant DB pool
from each incoming signed request. No production overrides/config changes.
Unsupported pre-auth routes fail closed (Login, Refresh, WhatsApp, Ready).
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.enterprise_models import PatientConsentChallenge, PortalAccess
from app.main import app
from app.security import token_for
from app.staged_http_tenant_router import StagedHttpTenantRouter
from app.tenant_route_tokens import TenantRouteKeyring, token_sha256


@dataclass(frozen=True)
class Identity:
    id: str
    tenant_id: str
    role: str


def env(field: str) -> str:
    return os.environ["PROBE_" + field]


def assert_status(response, code, description):
    assert response.status_code == code, (
        f"{description}: expected {code}, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    return response.json() if response.content else None


def make_pool(role: str, password: str):
    url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host="medtour-test-db", port=5432, database="medtour_principal_clone",
    )
    engine = create_engine(
        url, pool_size=3, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback", connect_args={"connect_timeout": 5},
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def main():
    if (os.getenv("APP_ENV") != "test"
            or os.getenv("DATABASE_URL") != "sqlite://"
            or os.getenv("PROBE_DB_HOST") != "medtour-test-db"):
        raise RuntimeError("HTTP tenant router proof requires a synthetic isolated clone")

    tids = [env("TENANT_A"), env("TENANT_B")]
    pids = [env("PATIENT_A"), env("PATIENT_B")]
    uids = [env("USER_A"), env("USER_B")]
    engines = []
    signing = TenantRouteKeyring(
        {"stage": secrets.token_bytes(32)}, active_key_id="stage",
    )
    pools = {}
    tokens = {}
    checkouts = [0]

    try:
        for index, role in enumerate(("mt_clone_a", "mt_clone_b")):
            engine, factory = make_pool(role, env("PASSWORD_A" if index == 0 else "PASSWORD_B"))
            engines.append(engine)
            pools[tids[index]] = factory
            with factory() as db:
                portal = signing.issue(
                    purpose="portal", tenant_id=tids[index], ttl_seconds=1800,
                )
                consent = signing.issue(
                    purpose="consent", tenant_id=tids[index], ttl_seconds=900,
                )
                tokens[tids[index]] = {"portal": portal, "consent": consent}
                db.add_all([
                    PortalAccess(
                        tenant_id=tids[index], patient_id=pids[index],
                        issued_by=uids[index], token_hash=token_sha256(portal),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                    ),
                    PatientConsentChallenge(
                        tenant_id=tids[index], patient_id=pids[index],
                        issued_by=uids[index], token_hash=token_sha256(consent),
                        purpose="communication",
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                    ),
                ])
                db.commit()

            @event.listens_for(engine, "checkout")
            def count_checkout(dbapi_connection, connection_record, connection_proxy):
                checkouts[0] += 1

        router = StagedHttpTenantRouter(keyring=signing, sessions_by_tenant=pools)
        app.dependency_overrides[get_db] = router.get_db
        identities = [
            Identity(uids[0], tids[0], "admin"),
            Identity(uids[1], tids[1], "admin"),
        ]
        auth = [
            {"Authorization": "Bearer " + token_for(user)}
            for user in identities
        ]
        with TestClient(app, raise_server_exceptions=False) as client:
            for index, tenant_id in enumerate(tids):
                assert assert_status(
                    client.get("/api/v1/auth/me", headers=auth[index]),
                    200, "Own signed staff identity"
                )["tenant_id"] == tenant_id
                listed = assert_status(
                    client.get("/api/v1/patients", headers=auth[index]), 200,
                    "Current tenant patient listing",
                )
                assert any(x["id"] == pids[index] for x in listed)
                assert all(x["id"] != pids[1-index] for x in listed)
                assert_status(
                    client.get(f"/api/v1/patients/{pids[index]}", headers=auth[index]),
                    200, "Own patient",
                )
                assert_status(
                    client.get(f"/api/v1/patients/{pids[1-index]}", headers=auth[index]),
                    404, "Cross-tenant patient IDOR",
                )
                assert_status(
                    client.get("/api/v1/auth/me", headers={
                        **auth[index], "X-Tenant-ID": tids[1-index],
                    }), 200, "Untrusted tenant header ignored",
                )
                print(f"PASS: real HTTP staff JWT selects tenant {index+1} pool with RLS", flush=True)

                assert assert_status(
                    client.get("/api/v1/portal/me", headers={
                        "X-Patient-Access": tokens[tenant_id]["portal"],
                    }), 200, "Own signed portal token"
                )["id"] == pids[index]
                assert assert_status(
                    client.get("/api/v1/consent-links/preview", params={
                        "token": tokens[tenant_id]["consent"],
                    }), 200, "Own signed consent preview"
                )["purpose"] == "communication"
                print(f"PASS: real HTTP portal and consent route by token MAC and DB hash for tenant {index+1}", flush=True)

            forged = tokens[tids[0]]["portal"].split(".")
            forged[3] = tids[1]
            count_before = checkouts[0]
            assert_status(client.get("/api/v1/portal/me", headers={
                "X-Patient-Access": ".".join(forged)
            }), 401, "Forged patient routing token")
            assert checkouts[0] == count_before, "Forged token reached PostgreSQL"

            assert_status(client.get("/api/v1/patients"), 401, "No JWT")
            assert_status(client.get("/api/v1/patients", headers={
                "Authorization": "Bearer invalid-staff-jwt"
            }), 401, "Invalid staff JWT")
            assert_status(client.get("/api/v1/portal/me", headers={
                "X-Patient-Access": secrets.token_urlsafe(48)
            }), 401, "Legacy opaque portal token")
            assert checkouts[0] == count_before, "Invalid credentials opened a DB connection"
            print("PASS: unsigned/malformed tokens rejected before checkout", flush=True)

            # A legitimately MAC-signed-but-mismatched server pool is denied.
            swapped = StagedHttpTenantRouter(keyring=signing, sessions_by_tenant={
                tids[0]: pools[tids[1]], tids[1]: pools[tids[0]],
            })
            app.dependency_overrides[get_db] = swapped.get_db
            assert_status(
                client.get("/api/v1/auth/me", headers=auth[0]), 401,
                "Wrong authenticated PostgreSQL principal for token",
            )
            app.dependency_overrides[get_db] = router.get_db
            print("PASS: wrong server-side pool mapping fails closed", flush=True)

            # Existing login and refresh endpoints depend on global lookups or
            # issue legacy unrouteable tokens, so explicitly refuse activation.
            assert_status(client.post("/api/v1/auth/login", json={
                "tenant_slug": "principal-poc-a",
                "email": "admin-a@synthetic.invalid",
                "password": "synthetic-password-not-valid",
            }), 503, "Login without trusted registry")
            assert_status(client.post("/api/v1/auth/refresh", json={
                "refresh_token": "x" * 64
            }), 503, "Legacy refresh route")
            assert_status(client.get("/api/v1/health/ready"), 503, "Global tenant registry check")
            assert_status(client.post("/api/v1/webhooks/whatsapp", json={}), 503, "Unmigrated WhatsApp webhook")
            print("PASS: login/refresh/ready/webhook remain fail-closed", flush=True)

            # Real pre-auth consent respond handler must route to A, consume
            # signed credential exactly once and deny a replay.
            a_consent = tokens[tids[0]]["consent"]
            assert_status(client.post("/api/v1/consent-links/respond", json={
                "token": a_consent, "notice_version": "stage-19-20",
                "accepted": True,
            }), 201, "Consent A recorded")
            assert_status(client.post("/api/v1/consent-links/respond", json={
                "token": a_consent, "notice_version": "stage-19-20",
                "accepted": True,
            }), 401, "Consent A replay")
            print("PASS: actual HTTP consent response and replay under correct tenant role", flush=True)

            # Withdrawing communication consent invalidates patient's portal.
            b_consent = tokens[tids[1]]["consent"]
            assert_status(client.post("/api/v1/consent-links/respond", json={
                "token": b_consent, "notice_version": "stage-19-20",
                "accepted": False,
            }), 201, "Consent B withdrawal")
            assert_status(client.get("/api/v1/portal/me", headers={
                "X-Patient-Access": tokens[tids[1]]["portal"],
            }), 401, "Withdrawing consent revokes portal")
            assert_status(client.get("/api/v1/portal/me", headers={
                "X-Patient-Access": tokens[tids[0]]["portal"],
            }), 200, "Tenant A portal unaffected by B")
            print("PASS: actual HTTP consent withdrawal revokes only owned portal", flush=True)

        print("PASS: STAGE 19.20 ISOLATED REQUEST-BOUND FASTAPI TENANT ROUTING TEST COMPLETED", flush=True)
        print("LIMITATION: adapter is test-only; no runtime get_db, Login, Refresh, Webhook or Alembic migrations changed", flush=True)
    finally:
        app.dependency_overrides.clear()
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
