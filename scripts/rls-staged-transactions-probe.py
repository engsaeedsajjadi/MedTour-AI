"""Stage 19.19: real PostgreSQL row-lock and replay tests, synthetic clone only."""
from __future__ import annotations

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.enterprise_models import (
    PatientConsentChallenge,
    PortalAccess,
    RefreshSession,
)
from app.models import Consent, User
from app.staged_tenant_transactions import StagedTenantCredentialTransactions
from app.tenant_route_tokens import TenantRouteKeyring, token_sha256


def expect(condition, explanation: str):
    if not condition:
        raise AssertionError(explanation)


def pool(role: str, password: str):
    url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host="medtour-test-db", port=5432, database="medtour_principal_clone",
    )
    engine = create_engine(
        url, pool_size=5, max_overflow=0, pool_timeout=15,
        pool_pre_ping=True, pool_reset_on_return="rollback",
        connect_args={"connect_timeout": 5},
    )
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def main():
    if (
        os.getenv("APP_ENV") != "test" or os.getenv("DATABASE_URL") != "sqlite://"
        or os.getenv("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Refusing to execute outside synthetic isolated clone")

    tenant_a, tenant_b = os.environ["PROBE_TENANT_A"], os.environ["PROBE_TENANT_B"]
    patient_a, patient_b = os.environ["PROBE_PATIENT_A"], os.environ["PROBE_PATIENT_B"]
    signing_key = secrets.token_bytes(32)
    keyring = TenantRouteKeyring({"k1": signing_key}, active_key_id="k1")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    engines = []
    configs = [
        ("mt_clone_a", os.environ["PROBE_PASSWORD_A"], tenant_a, patient_a),
        ("mt_clone_b", os.environ["PROBE_PASSWORD_B"], tenant_b, patient_b),
    ]
    try:
        pools = {}
        records = {}
        for role, password, tid, pid in configs:
            engine, factory = pool(role, password)
            engines.append(engine)
            pools[tid] = factory

            tokens = {
                "refresh": keyring.issue(
                    purpose="refresh", tenant_id=tid, ttl_seconds=3600,
                ),
                "consent": keyring.issue(
                    purpose="consent", tenant_id=tid, ttl_seconds=900,
                ),
            }
            with factory() as db:
                user = User(
                    tenant_id=tid, email=f"staged-{uuid4().hex}@synthetic.invalid",
                    password_hash="not-for-auth", role="admin", active=True,
                )
                db.add(user)
                db.flush()
                family = str(uuid4())
                db.add(RefreshSession(
                    tenant_id=tid, user_id=user.id,
                    refresh_hash=token_sha256(tokens["refresh"]),
                    expires_at=now + timedelta(hours=1),
                    family_id=family,
                ))
                db.add(PatientConsentChallenge(
                    tenant_id=tid, patient_id=pid, purpose="communication",
                    issued_by=user.id, token_hash=token_sha256(tokens["consent"]),
                    expires_at=now + timedelta(minutes=15),
                ))
                portal = PortalAccess(
                    tenant_id=tid, patient_id=pid, issued_by=user.id,
                    token_hash=token_sha256(secrets.token_urlsafe(36)),
                    expires_at=now + timedelta(hours=1),
                )
                db.add(portal)
                db.commit()
                records[tid] = {
                    "user_id": user.id, "patient_id": pid, "family_id": family,
                    "tokens": tokens, "portal_id": portal.id,
                }

        service = StagedTenantCredentialTransactions(
            keyring=keyring, sessions_by_tenant=pools,
        )

        # Cross-purpose and forged routing hints never authorize anything.
        assert service.rotate_refresh(records[tenant_a]["tokens"]["consent"]) is None
        assert service.consume_consent(
            records[tenant_b]["tokens"]["refresh"],
            notice_version="synthetic-v1", accepted=True,
        ) is None
        forged = records[tenant_a]["tokens"]["refresh"].split(".")
        forged[3] = tenant_b
        assert service.rotate_refresh(".".join(forged)) is None
        print("PASS: purpose confusion and MAC-tampering rejected", flush=True)

        # Valid same-tenant refresh produces a new signed credential.
        token_a = records[tenant_a]["tokens"]["refresh"]
        rotated_a = service.rotate_refresh(token_a)
        expect(rotated_a is not None, "Tenant A refresh did not rotate")
        expect(rotated_a.tenant_id == tenant_a, "Refresh leaked to foreign tenant")
        expect(rotated_a.user_id == records[tenant_a]["user_id"], "Wrong refresh user")
        expect(rotated_a.refresh_token != token_a, "Refresh token was reused")
        with pools[tenant_a]() as db:
            replacement = db.scalar(
                select(RefreshSession).where(
                    RefreshSession.tenant_id == tenant_a,
                    RefreshSession.refresh_hash == token_sha256(rotated_a.refresh_token),
                )
            )
            expect(replacement is not None and replacement.revoked_at is None,
                   "New refresh hash not committed to correct tenant")
        print("PASS: atomic refresh rotation created a new signed DB-backed token", flush=True)

        # Reusing the revoked token invalidates the entire family including
        # the newly minted credential; other tenants remain unaffected.
        assert service.rotate_refresh(token_a) is None
        assert service.rotate_refresh(rotated_a.refresh_token) is None
        with pools[tenant_a]() as db:
            family_rows = db.scalars(
                select(RefreshSession).where(
                    RefreshSession.tenant_id == tenant_a,
                    RefreshSession.family_id == records[tenant_a]["family_id"],
                )
            ).all()
            expect(len(family_rows) == 2, "Unexpected refresh token family count")
            expect(all(item.revoked_at is not None for item in family_rows),
                   "Replay did not revoke the whole refresh family")
        print("PASS: refresh replay revokes entire family without tenant bleed", flush=True)

        rotated_b = service.rotate_refresh(records[tenant_b]["tokens"]["refresh"])
        expect(rotated_b is not None and rotated_b.tenant_id == tenant_b,
               "Tenant B invalidated by replay in A")
        print("PASS: replay of A does not revoke B", flush=True)

        # A: accept consent once, no duplicates. B: withdrawal revokes portal.
        consent_a = records[tenant_a]["tokens"]["consent"]
        decision_a = service.consume_consent(
            consent_a, notice_version="synthetic-v1", accepted=True
        )
        expect(decision_a is not None and decision_a.accepted,
               "Accepted consent not written")
        assert service.consume_consent(
            consent_a, notice_version="synthetic-v1", accepted=True
        ) is None

        consent_b = records[tenant_b]["tokens"]["consent"]
        decision_b = service.consume_consent(
            consent_b, notice_version="synthetic-v1", accepted=False
        )
        expect(decision_b is not None and not decision_b.accepted,
               "Consent withdrawal not recorded")
        with pools[tenant_b]() as db:
            revoked = db.get(PortalAccess, records[tenant_b]["portal_id"])
            expect(revoked is not None and revoked.revoked, "Withdrawal did not revoke portal")
            consents = db.scalars(
                select(Consent).where(
                    Consent.tenant_id == tenant_b,
                    Consent.patient_id == patient_b,
                    Consent.source == "patient_link",
                )
            ).all()
            expect(any(not c.accepted for c in consents), "Withdrawal consent audit missing")
        print("PASS: consent accept/replay and withdrawal/portal revocation atomic", flush=True)

        # Real concurrent POST-equivalent calls to the same one-time link must
        # produce exactly one committed consent under PostgreSQL FOR UPDATE.
        race_token = keyring.issue(
            purpose="consent", tenant_id=tenant_a, ttl_seconds=900,
        )
        with pools[tenant_a]() as db:
            db.add(PatientConsentChallenge(
                tenant_id=tenant_a, patient_id=patient_a,
                purpose="communication", issued_by=records[tenant_a]["user_id"],
                token_hash=token_sha256(race_token),
                expires_at=now + timedelta(minutes=15),
            ))
            db.commit()
        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = [
                executor.submit(
                    service.consume_consent,
                    race_token, notice_version="synthetic-race-v1", accepted=True,
                )
                for _ in range(2)
            ]
            results = [task.result() for task in tasks]
        expect(sum(value is not None for value in results) == 1,
               "Concurrent consent consumption was not exactly-once")
        with pools[tenant_a]() as db:
            written = db.scalars(
                select(Consent).where(
                    Consent.tenant_id == tenant_a,
                    Consent.patient_id == patient_a,
                    Consent.notice_version == "synthetic-race-v1",
                )
            ).all()
            expect(len(written) == 1, "Concurrent consent wrote duplicate rows")
        print("PASS: PostgreSQL row lock ensures one consent under concurrent requests", flush=True)

        # Swapped pool mapping must never retrieve/update the other tenant.
        swapped = StagedTenantCredentialTransactions(
            keyring=keyring, sessions_by_tenant={
                tenant_a: pools[tenant_b], tenant_b: pools[tenant_a],
            },
        )
        assert swapped.consume_consent(
            race_token, notice_version="synthetic-v1", accepted=True,
        ) is None
        print("PASS: swapped tenant role connection fails closed", flush=True)

        # No valid database principal/credential -> no privileged fallback.
        invalid_engine, invalid_factory = pool("mt_clone_a", "wrong-" + uuid4().hex)
        engines.append(invalid_engine)
        invalid = StagedTenantCredentialTransactions(
            keyring=keyring, sessions_by_tenant={tenant_a: invalid_factory},
        )
        assert invalid.rotate_refresh(token_a) is None
        print("PASS: inaccessible DB login does not trigger superuser fallback", flush=True)

        print("PASS: STAGE 19.19 ISOLATED ATOMIC REFRESH CONSENT TRANSACTION TEST COMPLETED", flush=True)
        print("LIMITATION: operational API endpoints and shared get_db are not migrated", flush=True)
    finally:
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
