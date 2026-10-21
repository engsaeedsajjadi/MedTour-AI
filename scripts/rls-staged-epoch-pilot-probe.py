"""Operational migration pilot — REAL PostgreSQL clone, staged FastAPI only.

Proves that Login, Refresh and Meta validation all acquire DB sessions
through a tenant role + uncached central epoch lease, not the legacy get_db.
No PHI is processed; no production ASGI app, migration or Compose service.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.enterprise_models import MessageEvent
from app.models import User
from app.security import password_hash
from app.staged_epoch_preauth_bridge import create_clone_preauth_pilot, EpochGuardedSessionFactory
from app.staged_tenant_epoch_control import PostgreSQLEpochReader, StagedCoordinatedTenantRegistry
from app.staged_tenant_pool_registry import TenantPrincipalConfig
from app.tenant_route_tokens import TenantRouteKeyring
from app.rate_limit import _hits


def env(key):
    return os.environ["PROBE_" + key]


def make_engine(role, password):
    return create_engine(
        URL.create(
            "postgresql+psycopg", username=role, password=password,
            host="medtour-test-db", port=5432, database="medtour_principal_clone",
        ),
        pool_size=2, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback", connect_args={"connect_timeout": 5},
    )


def spec(letter):
    return TenantPrincipalConfig(
        tenant_id=env("TENANT_" + letter),
        slug="principal-poc-" + letter.lower(),
        whatsapp_phone_id="synthetic-phone-" + letter.lower(),
        database_role="mt_clone_" + letter.lower(),
        database_password=env("PASSWORD_" + letter),
        database_host="medtour-test-db", database_name="medtour_principal_clone",
    )


def code(response, expected):
    assert response.status_code == expected, (
        f"HTTP {response.status_code} expected {expected}: {response.text[:250]}"
    )
    return response.json() if response.content else None


def login(client, letter, password):
    return client.post("/api/v1/auth/login", json={
        "tenant_slug": "principal-poc-" + letter.lower(),
        "email": "admin-" + letter.lower() + "@synthetic.invalid",
        "password": password,
    })


def meta_payload(phone):
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone}, "messages": []
        }}]}],
    }, separators=(",", ":")).encode()


def signed(body, secret):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def check_meta(client, phone, secret, expected):
    raw = meta_payload(phone)
    return code(client.post(
        "/api/v1/webhooks/whatsapp", content=raw,
        headers={"X-Hub-Signature-256": signed(raw, secret)}
    ), expected)


def switch_epoch(writer, tenant, before, enabled):
    with writer.begin() as conn:
        return conn.execute(text(
            "UPDATE medtour_control.tenant_epochs "
            "SET generation=generation+1,enabled=:enabled "
            "WHERE tenant_id=:tid AND generation=:before "
            "RETURNING generation"
        ), {"enabled": enabled, "tid": tenant, "before": before}).scalar_one()


def main():
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DATABASE_URL") != "sqlite://"
        or os.environ.get("MEDTOUR_SYNTHETIC_CLONE") != "1"
        or os.environ.get("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Synthetic-only pilot requires all clone guards")

    a, b = spec("A"), spec("B")
    _hits.clear()
    reader_engines = [
        make_engine("mt_control_reader", env("CONTROL_READ_PASSWORD"))
        for _ in range(2)
    ]
    writer = make_engine("mt_control_writer", env("CONTROL_WRITE_PASSWORD"))
    registries = [
        StagedCoordinatedTenantRegistry(
            reader=PostgreSQLEpochReader(r), max_tenants=2, pool_size=2
        )
        for r in reader_engines
    ]
    password = "synthetic-pilot-staff-password-2026"
    meta_secret = "synthetic-pilot-meta-secret-never-for-real-traffic"
    keyring = TenantRouteKeyring({"stage": bytes(range(32))}, "stage")
    try:
        for registry in registries:
            registry.provision(a, generation=1)
            registry.provision(b, generation=1)
        # Only synthetic users in disposable DB. Every fixture update itself
        # passes through the role pool and central-epoch checked lease.
        for letter, cfg in (("A", a), ("B", b)):
            with EpochGuardedSessionFactory(registries[0], cfg.tenant_id)() as db:
                user = db.get(User, env("USER_" + letter))
                assert user and user.tenant_id == cfg.tenant_id
                user.password_hash = password_hash(password)
                db.commit()

        clients = []
        for registry in registries:
            application = create_clone_preauth_pilot(
                registry=registry, provisioned={a.tenant_id: a, b.tenant_id: b},
                keyring=keyring, meta_app_secret=meta_secret, whatsapp_approved=True,
            )
            clients.append(TestClient(application, raise_server_exceptions=False))
        for client in clients:
            for letter, cfg in (("A", a), ("B", b)):
                success = code(login(client, letter, password), 200)
                assert success["tenant_id"] == cfg.tenant_id
                assert success["refresh_token"]
                assert success["access_token"]
                rotated = code(client.post("/api/v1/auth/refresh", json={
                    "refresh_token": success["refresh_token"]
                }), 200)
                assert rotated["refresh_token"] != success["refresh_token"]
                message = check_meta(client, cfg.whatsapp_phone_id, meta_secret, 200)
                assert message["processed_messages"] == 0
                assert message["validated_only"] is True
                assert message["received"] is False
        print("PASS: two isolated FastAPI pilots login, refresh, validate Meta via epoch-guarded RLS pools", flush=True)

        # Verify there was no persistence/PHI processing from accepted webhook.
        with EpochGuardedSessionFactory(registries[0], a.tenant_id)() as db:
            before_a = db.scalar(
                select(func.count()).select_from(MessageEvent).where(
                    MessageEvent.tenant_id == a.tenant_id
                )
            )
        assert switch_epoch(writer, a.tenant_id, 1, False) == 2
        for client in clients:
            code(login(client, "A", password), 401)
            check_meta(client, a.whatsapp_phone_id, meta_secret, 403)
            data_b = code(login(client, "B", password), 200)
            assert data_b["tenant_id"] == b.tenant_id
            check_meta(client, b.whatsapp_phone_id, meta_secret, 200)
        assert all(reg.snapshot_counts()["tenants"] == 1 for reg in registries)
        print("PASS: disabling tenant A epoch denies HTTP login and signed Meta on both workers, B healthy", flush=True)

        # A refresh credential from an otherwise healthy tenant must not be
        # used after its epoch is disabled — even when its MAC is valid.
        scoped_raw = keyring.issue(purpose="refresh", tenant_id=a.tenant_id, ttl_seconds=3600)
        for client in clients:
            code(client.post("/api/v1/auth/refresh", json={
                "refresh_token": scoped_raw
            }), 401)
        print("PASS: MAC-valid refresh token cannot bypass central epoch disable", flush=True)

        assert switch_epoch(writer, a.tenant_id, 2, True) == 3
        for registry in registries:
            try:
                registry.provision(a, generation=1)
            except LookupError:
                pass
            else:
                raise AssertionError("Stale generation accepted after enable")
            registry.provision(a, generation=3)
        for client in clients:
            again = code(login(client, "A", password), 200)
            assert again["tenant_id"] == a.tenant_id
            check_meta(client, a.whatsapp_phone_id, meta_secret, 200)
        with EpochGuardedSessionFactory(registries[0], a.tenant_id)() as db:
            after_a = db.scalar(
                select(func.count()).select_from(MessageEvent).where(
                    MessageEvent.tenant_id == a.tenant_id
                )
            )
            assert before_a == after_a
        print("PASS: explicit generation-3 reprovisioning restores only approved staged routes", flush=True)
        print("PASS: validated-only WhatsApp pilot persisted no message events or PHI", flush=True)
        print("PASS: STAGED RUNTIME MIGRATION PILOT ISOLATED EPOCH PREAUTH FASTAPI TEST COMPLETED", flush=True)
        print("LIMITATION: no live get_db migration, no PHI endpoints, no multi-process deployment", flush=True)
    finally:
        for registry in registries:
            registry.close()
        for engine in reader_engines:
            engine.dispose()
        writer.dispose()


if __name__ == "__main__":
    main()
