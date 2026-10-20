"""Stage 19.16 — FastAPI TestClient against real tenant-specific PostgreSQL LOGIN roles.

Never invoked by production application. Only run inside offline ephemeral Docker
network + restored synthetic backup. Overrides FastAPI get_db per test client, so
this PROVES scoped endpoint behavior, NOT production tenant principal selection.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.security import token_for


@dataclass(frozen=True)
class Identity:
    id: str
    tenant_id: str
    role: str


def env(key: str) -> str:
    return os.environ["PROBE_" + key]


def must(response, status: int, label: str):
    assert response.status_code == status, (
        f"{label}: expected HTTP {status}, got {response.status_code}; "
        f"body={response.text[:300]}"
    )
    return response.json() if response.content else None


def client_for(role: str, password: str):
    db_url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host=env("DB_HOST"), database="medtour_principal_clone", port=5432
    )
    engine = create_engine(
        db_url, pool_size=2, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback", connect_args={"connect_timeout": 5},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def tenant_session():
        with factory() as session:
            yield session

    return engine, tenant_session


def main():
    engines = []
    try:
        for role, passkey, own_tid in (
            ("mt_clone_a", "PASSWORD_A", "TENANT_A"),
            ("mt_clone_b", "PASSWORD_B", "TENANT_B"),
        ):
            engine, scoped = client_for(role, env(passkey))
            engines.append(engine)
            with engine.connect() as conn:
                assert conn.execute(text("SELECT current_user")).scalar_one() == role
                assert conn.execute(text("SELECT session_user")).scalar_one() == role
            app.dependency_overrides[get_db] = scoped
            user_a = Identity(env("USER_A"), env("TENANT_A"), "admin")
            user_b = Identity(env("USER_B"), env("TENANT_B"), "admin")
            own = user_a if role == "mt_clone_a" else user_b
            foreign = user_b if role == "mt_clone_a" else user_a
            own_patient = env("PATIENT_A") if role == "mt_clone_a" else env("PATIENT_B")
            foreign_patient = env("PATIENT_B") if role == "mt_clone_a" else env("PATIENT_A")
            own_portal = env("PORTAL_A") if role == "mt_clone_a" else env("PORTAL_B")
            foreign_portal = env("PORTAL_B") if role == "mt_clone_a" else env("PORTAL_A")
            own_consent = env("CONSENT_A") if role == "mt_clone_a" else env("CONSENT_B")
            foreign_consent = env("CONSENT_B") if role == "mt_clone_a" else env("CONSENT_A")
            own_refresh = env("REFRESH_A") if role == "mt_clone_a" else env("REFRESH_B")
            foreign_refresh = env("REFRESH_B") if role == "mt_clone_a" else env("REFRESH_A")
            own_headers = {"Authorization": "Bearer " + token_for(own)}
            foreign_headers = {"Authorization": "Bearer " + token_for(foreign)}

            with TestClient(app, raise_server_exceptions=False) as client:
                must(client.get("/api/v1/auth/me", headers=own_headers),
                     200, f"{role} own JWT")
                must(client.get("/api/v1/auth/me", headers=foreign_headers),
                     401, f"{role} foreign valid JWT")
                print(f"PASS: {role} JWT user validation enforces PostgreSQL principal", flush=True)

                patients = must(client.get("/api/v1/patients", headers=own_headers),
                                200, f"{role} list")
                assert any(p["id"] == own_patient for p in patients)
                assert all(p["id"] != foreign_patient for p in patients)
                must(client.get(f"/api/v1/patients/{own_patient}", headers=own_headers),
                     200, f"{role} own patient")
                must(client.get(f"/api/v1/patients/{foreign_patient}", headers=own_headers),
                     404, f"{role} foreign patient IDOR")
                must(client.get("/api/v1/patients", headers=foreign_headers),
                     401, f"{role} foreign JWT patients")
                print(f"PASS: {role} patient list, detail and IDOR isolation", flush=True)

                created = must(client.post(
                    "/api/v1/patients", headers=own_headers,
                    json={"full_name": "Synthetic HTTP integration patient", "language": "en"},
                ), 201, f"{role} patient CREATE")
                assert created["tenant_id"] == own.tenant_id
                print(f"PASS: {role} FastAPI writes through its authenticated DB role", flush=True)

                portal_headers = {"X-Patient-Access": own_portal}
                foreign_portal_headers = {"X-Patient-Access": foreign_portal}
                assert must(client.get("/api/v1/portal/me", headers=portal_headers),
                            200, f"{role} own portal")["id"] == own_patient
                must(client.get("/api/v1/portal/me", headers=foreign_portal_headers),
                     401, f"{role} foreign portal")
                assert must(client.get("/api/v1/consent-links/preview",
                                       params={"token": own_consent}),
                            200, f"{role} own consent preview")["purpose"] == "communication"
                must(client.get("/api/v1/consent-links/preview",
                                params={"token": foreign_consent}),
                     401, f"{role} foreign consent preview")
                print(f"PASS: {role} portal and consent tokens are tenant-isolated", flush=True)

                must(client.post("/api/v1/auth/refresh",
                                 json={"refresh_token": foreign_refresh}),
                     401, f"{role} foreign refresh")
                rotated = must(client.post("/api/v1/auth/refresh",
                                           json={"refresh_token": own_refresh}),
                               200, f"{role} own refresh")
                assert rotated["access_token"] and rotated["refresh_token"]
                must(client.post("/api/v1/auth/refresh",
                                 json={"refresh_token": own_refresh}),
                     401, f"{role} replayed refresh")
                print(f"PASS: {role} refresh rotation and replay protected by its DB principal",
                      flush=True)

                if role == "mt_clone_a":
                    auditor = Identity(env("AUDITOR_A"), env("TENANT_A"), "auditor")
                    audit_headers = {"Authorization": "Bearer " + token_for(auditor)}
                    must(client.get("/api/v1/auth/me", headers=audit_headers),
                         200, "Auditor identity")
                    must(client.get("/api/v1/patients", headers=audit_headers),
                         403, "Auditor access to protected patients")
                    print("PASS: authenticated auditor receives 403 for restricted endpoint", flush=True)
            app.dependency_overrides.clear()
        print("PASS: STAGE 19.16 ISOLATED FASTAPI POSTGRESQL RLS ENDPOINT PROOF COMPLETED", flush=True)
        print("LIMITATION: get_db overridden only inside test; production Login/Webhook/TokenResolver and connection routing are NOT enabled", flush=True)
    finally:
        app.dependency_overrides.clear()
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
