"""Stage 19.21: REAL HTTP login/refresh + Meta signature tenant-routing proof.

Standalone FastAPI TestClient with a staged router; operates only on a restored
synthetic PostgreSQL clone and role-specific DB logins. The production main.py
and its global get_db remain unchanged. Webhook validation NEVER processes PHI.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.enterprise_models import RefreshSession
from app.models import User
from app.security import password_hash
from app.staged_preauth_service import StagedPreAuthService
from app.staged_preauth_http import staged_preauth_router
from app.tenant_route_tokens import TenantRouteKeyring, token_sha256
from app.rate_limit import _hits


def env(name: str) -> str:
    return os.environ["PROBE_" + name]


def pool(role: str, password: str):
    url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host="medtour-test-db", port=5432, database="medtour_principal_clone",
    )
    engine = create_engine(
        url, pool_size=3, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback", connect_args={"connect_timeout": 5},
    )
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def status(response, expected: int, label: str):
    assert response.status_code == expected, (
        f"{label}: HTTP {response.status_code} expected {expected}: "
        f"{response.text[:250]}"
    )
    return response.json() if response.content else None


def signed(raw: bytes, secret: str):
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def webhook_body(phone_ids):
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {"metadata": {"phone_number_id": p}, "messages": []},
            } for p in phone_ids],
        }],
    }, separators=(",", ":")).encode()


def main():
    if (
        os.environ.get("APP_ENV") != "test" or
        os.environ.get("DATABASE_URL") != "sqlite://" or
        os.environ.get("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Stage 19.21 must run inside the isolated clone only")
    _hits.clear()
    tids = [env("TENANT_A"), env("TENANT_B")]
    uids = [env("USER_A"), env("USER_B")]
    roles = ("mt_clone_a", "mt_clone_b")
    secrets_roles = (env("PASSWORD_A"), env("PASSWORD_B"))
    good_password = "stage-19-21-synthetic-credential"
    secret_meta = "stage-19-21-offline-meta-app-signing-secret"
    engines = []
    factories = {}
    try:
        for i, role in enumerate(roles):
            engine, factory = pool(role, secrets_roles[i])
            engines.append(engine)
            factories[tids[i]] = factory
            with factory() as db:
                user = db.get(User, uids[i])
                assert user is not None and user.tenant_id == tids[i]
                user.password_hash = password_hash(good_password)
                db.commit()
                # Runtime roles are not entitled to read the global registry.
                try:
                    db.execute(text("SELECT count(*) FROM public.tenants")).scalar_one()
                except DBAPIError as exc:
                    assert getattr(exc.orig, "sqlstate", None) == "42501"
                    db.rollback()
                else:
                    raise AssertionError("Runtime role unexpectedly reads tenant registry")
        print("PASS: two tenant roles authenticate independently without global tenants SELECT", flush=True)

        keyring = TenantRouteKeyring(
            {"stage": bytes(range(32))}, active_key_id="stage"
        )
        service = StagedPreAuthService(
            keyring=keyring,
            sessions_by_tenant=factories,
            tenant_slugs={
                "principal-poc-a": tids[0],
                "principal-poc-b": tids[1],
            },
            whatsapp_accounts={
                "synthetic-phone-a": tids[0],
                "synthetic-phone-b": tids[1],
            },
            whatsapp_app_secret=secret_meta,
            whatsapp_approved=True,
        )
        application = FastAPI()
        application.include_router(staged_preauth_router(service))

        with TestClient(application, raise_server_exceptions=False) as client:
            data = []
            for i, slug in enumerate(("principal-poc-a", "principal-poc-b")):
                response = status(client.post("/api/v1/auth/login", json={
                    "tenant_slug": slug,
                    "email": f"admin-{'a' if i == 0 else 'b'}@synthetic.invalid",
                    "password": good_password,
                }), 200, "Scoped staff login")
                assert response["tenant_id"] == tids[i]
                claims = jwt.decode(
                    response["access_token"], os.environ["JWT_SECRET"],
                    algorithms=["HS256"],
                )
                assert claims["tid"] == tids[i] and claims["sub"] == uids[i]
                assert keyring.verify(
                    response["refresh_token"], expected_purpose="refresh"
                ).tenant_id == tids[i]
                with factories[tids[i]]() as db:
                    found = db.scalar(select(RefreshSession).where(
                        RefreshSession.tenant_id == tids[i],
                        RefreshSession.refresh_hash == token_sha256(
                            response["refresh_token"]
                        ),
                    ))
                    assert found is not None
                data.append(response)
                print(f"PASS: tenant {i+1} real HTTP login issues correctly scoped JWT and MAC refresh", flush=True)

            assert status(client.post("/api/v1/auth/login", json={
                "tenant_slug": "principal-poc-b",
                "email": "admin-a@synthetic.invalid",
                "password": good_password,
            }), 401, "Cross-tenant account login") is not None
            status(client.post("/api/v1/auth/login", json={
                "tenant_slug": "non-existent-tenant",
                "email": "admin-a@synthetic.invalid",
                "password": good_password,
            }), 401, "Invalid tenant slug")
            status(client.post("/api/v1/auth/login", json={
                "tenant_slug": "principal-poc-a",
                "email": "admin-a@synthetic.invalid",
                "password": "incorrect-password",
            }), 401, "Incorrect staff password")
            print("PASS: tenant slug, cross-tenant account and incorrect credentials are denied", flush=True)

            rotated_a = status(client.post("/api/v1/auth/refresh", json={
                "refresh_token": data[0]["refresh_token"],
            }), 200, "Refresh rotation A")
            assert rotated_a["refresh_token"] != data[0]["refresh_token"]
            assert keyring.verify(
                rotated_a["refresh_token"], expected_purpose="refresh"
            ).tenant_id == tids[0]
            assert jwt.decode(
                rotated_a["access_token"], os.environ["JWT_SECRET"],
                algorithms=["HS256"],
            )["tid"] == tids[0]
            status(client.post("/api/v1/auth/refresh", json={
                "refresh_token": data[0]["refresh_token"],
            }), 401, "Replay A original credential")
            status(client.post("/api/v1/auth/refresh", json={
                "refresh_token": rotated_a["refresh_token"],
            }), 401, "Replayed family now invalid")
            rotated_b = status(client.post("/api/v1/auth/refresh", json={
                "refresh_token": data[1]["refresh_token"],
            }), 200, "B not affected by A replay")
            assert rotated_b["refresh_token"]
            print("PASS: refresh rotation, replay-family revocation and cross-tenant independence", flush=True)

            for i, phone in enumerate(("synthetic-phone-a", "synthetic-phone-b")):
                raw = webhook_body([phone])
                result = status(client.post(
                    "/api/v1/webhooks/whatsapp", content=raw,
                    headers={"X-Hub-Signature-256": signed(raw, secret_meta)},
                ), 200, "Meta signed configured account")
                assert result["validated_only"] is True
                assert result["processed_messages"] == 0
                assert result["tenant_id"] == tids[i]
            bad = webhook_body(["synthetic-phone-a"])
            status(client.post(
                "/api/v1/webhooks/whatsapp", content=bad,
                headers={"X-Hub-Signature-256": signed(bad, "incorrect-secret")},
            ), 403, "Wrong Meta signature")
            unknown = webhook_body(["unknown-phone-id"])
            status(client.post(
                "/api/v1/webhooks/whatsapp", content=unknown,
                headers={"X-Hub-Signature-256": signed(unknown, secret_meta)},
            ), 403, "Unknown but signed business account")
            mixed = webhook_body(["synthetic-phone-a", "synthetic-phone-b"])
            status(client.post(
                "/api/v1/webhooks/whatsapp", content=mixed,
                headers={"X-Hub-Signature-256": signed(mixed, secret_meta)},
            ), 403, "Mixed-account payload")
            print("PASS: signed webhook binding, unknown account, mixed accounts and invalid MAC", flush=True)

        # Accidental wrong pre-provisioned connection cannot read/authenticate.
        swapped = StagedPreAuthService(
            keyring=keyring,
            sessions_by_tenant={tids[0]: factories[tids[1]],
                                tids[1]: factories[tids[0]]},
            tenant_slugs={"principal-poc-a": tids[0], "principal-poc-b": tids[1]},
            whatsapp_accounts={"synthetic-phone-a": tids[0]},
            whatsapp_app_secret=secret_meta, whatsapp_approved=True,
        )
        assert swapped.login("principal-poc-a", "admin-a@synthetic.invalid", good_password) is None
        raw = webhook_body(["synthetic-phone-a"])
        assert swapped.verify_webhook_route(raw, signed(raw, secret_meta)) is None
        closed = StagedPreAuthService(
            keyring=keyring, sessions_by_tenant=factories,
            tenant_slugs={"principal-poc-a": tids[0]},
            whatsapp_accounts={"synthetic-phone-a": tids[0]},
            whatsapp_app_secret=secret_meta, whatsapp_approved=False,
        )
        assert closed.verify_webhook_route(raw, signed(raw, secret_meta)) is None
        print("PASS: swapped PostgreSQL roles and non-approved webhook routing fail closed", flush=True)

        print("PASS: STAGE 19.21 ISOLATED PREAUTH LOGIN REFRESH WEBHOOK ROUTING TEST COMPLETED", flush=True)
        print("LIMITATION: main.py, global get_db, existing WhatsApp message processor and old refresh links remain unmodified", flush=True)
    finally:
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
