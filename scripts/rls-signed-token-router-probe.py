"""Stage 19.18 signed-token -> authenticated tenant DB principal -> stored hash.

Runs only in the network-isolated restored PostgreSQL clone. NOT the live API.
All patients/users/tokens used in this probe are synthetic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import os
import secrets

from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.enterprise_models import PatientConsentChallenge, PortalAccess, RefreshSession
from app.models import User
from app.tenant_route_tokens import TenantRouteKeyring, token_sha256
from app.tenant_credential_lookup import TenantCredentialLookup


def demand(value, description):
    if not value:
        raise AssertionError(description)


def new_pool(role, password):
    url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host="medtour-test-db", port=5432, database="medtour_principal_clone",
    )
    engine = create_engine(
        url, pool_size=2, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback", connect_args={"connect_timeout": 5},
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def main():
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DATABASE_URL") != "sqlite://"
        or os.environ.get("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Run only inside the offline synthetic PostgreSQL clone")

    tid_a, tid_b = os.environ["PROBE_TENANT_A"], os.environ["PROBE_TENANT_B"]
    patient_a, patient_b = os.environ["PROBE_PATIENT_A"], os.environ["PROBE_PATIENT_B"]
    keyring = TenantRouteKeyring({"k1": secrets.token_bytes(32)}, active_key_id="k1")
    epoch = datetime.now(timezone.utc).replace(microsecond=0)
    engines = []
    try:
        configs = (
            ("mt_clone_a", os.environ["PROBE_PASSWORD_A"], tid_a, patient_a),
            ("mt_clone_b", os.environ["PROBE_PASSWORD_B"], tid_b, patient_b),
        )
        pools = {}
        issued = {}
        rows = {}

        for role, password, tenant_id, patient_id in configs:
            engine, factory = new_pool(role, password)
            engines.append(engine)
            pools[tenant_id] = factory

            raw = {
                "refresh": keyring.issue(purpose="refresh", tenant_id=tenant_id, ttl_seconds=3600),
                "portal": keyring.issue(purpose="portal", tenant_id=tenant_id, ttl_seconds=1800),
                "consent": keyring.issue(purpose="consent", tenant_id=tenant_id, ttl_seconds=900),
            }
            issued[tenant_id] = raw

            with factory() as db:
                user = User(
                    tenant_id=tenant_id, email=f"probe-{uuid4().hex}@synthetic.invalid",
                    password_hash="not-for-login", role="admin", active=True,
                )
                db.add(user)
                db.flush()
                credentials = {
                    "refresh": RefreshSession(
                        tenant_id=tenant_id, user_id=user.id,
                        refresh_hash=token_sha256(raw["refresh"]),
                        family_id=str(uuid4()), expires_at=epoch + timedelta(hours=1),
                    ),
                    "portal": PortalAccess(
                        tenant_id=tenant_id, patient_id=patient_id,
                        token_hash=token_sha256(raw["portal"]),
                        issued_by=user.id, expires_at=epoch + timedelta(minutes=30),
                    ),
                    "consent": PatientConsentChallenge(
                        tenant_id=tenant_id, patient_id=patient_id,
                        token_hash=token_sha256(raw["consent"]),
                        purpose="communication", issued_by=user.id,
                        expires_at=epoch + timedelta(minutes=15),
                    ),
                }
                db.add_all(credentials.values())
                db.commit()
                rows[tenant_id] = {purpose: row.id for purpose, row in credentials.items()}

        resolver = TenantCredentialLookup(keyring=keyring, sessions_by_tenant=pools)
        for tenant_id, token_set in issued.items():
            for purpose, token in token_set.items():
                assert resolver.lookup(token, purpose=purpose) == rows[tenant_id][purpose]
            print("PASS: signed refresh, portal and consent locate their stored hashes under a single database principal", flush=True)

        for tid, token_set in issued.items():
            for purpose, token in token_set.items():
                assert resolver.lookup(token, purpose="portal" if purpose == "refresh" else "refresh") is None
                parts = token.split(".")
                parts[3] = tid_b if tid == tid_a else tid_a
                assert resolver.lookup(".".join(parts), purpose=purpose) is None
                parts = token.split(".")
                parts[-1] = ("A" if parts[-1][0] != "A" else "B") + parts[-1][1:]
                assert resolver.lookup(".".join(parts), purpose=purpose) is None
            print("PASS: cross-tenant forging and credential-purpose confusion fail before DB routing", flush=True)

        # A syntactically valid MAC is not authorization: missing DB hash denies.
        unissued = keyring.issue(purpose="portal", tenant_id=tid_a, ttl_seconds=300)
        assert resolver.lookup(unissued, purpose="portal") is None
        assert resolver.lookup(secrets.token_urlsafe(48), purpose="refresh") is None
        assert resolver.lookup(issued[tid_a]["portal"], purpose="portal",
                               now=epoch + timedelta(hours=1)) is None
        print("PASS: unsigned legacy, absent database hash and expired signed hint are denied", flush=True)

        # Deliberately wrong server mapping: authenticated PostgreSQL principal
        # must match the signed tenant even if a pool was configured incorrectly.
        swapped = TenantCredentialLookup(
            keyring=keyring, sessions_by_tenant={tid_a: pools[tid_b], tid_b: pools[tid_a]}
        )
        assert swapped.lookup(issued[tid_a]["portal"], purpose="portal") is None
        assert swapped.lookup(issued[tid_b]["refresh"], purpose="refresh") is None
        print("PASS: swapped tenant-to-pool configuration fails closed", flush=True)

        class ExplodingSession:
            def __call__(self):
                raise AssertionError("Invalid signature unexpectedly opened a DB session")

        no_db = TenantCredentialLookup(keyring=keyring, sessions_by_tenant={tid_a: ExplodingSession()})
        tampered = issued[tid_a]["portal"].replace("mt1.", "mt2.", 1)
        assert no_db.lookup(tampered, purpose="portal") is None
        print("PASS: invalid hint opens no database connection", flush=True)

        for role, password, tenant_id, patient_id in configs:
            with pools[tenant_id]() as db:
                refresh = db.scalar(
                    select(RefreshSession).where(RefreshSession.id == rows[tenant_id]["refresh"])
                )
                portal = db.scalar(
                    select(PortalAccess).where(PortalAccess.id == rows[tenant_id]["portal"])
                )
                consent = db.scalar(
                    select(PatientConsentChallenge).where(
                        PatientConsentChallenge.id == rows[tenant_id]["consent"]
                    )
                )
                refresh.revoked_at = datetime.now(timezone.utc)
                portal.revoked = True
                consent.used_at = datetime.now(timezone.utc)
                db.commit()
            for purpose in ("refresh", "portal", "consent"):
                assert resolver.lookup(issued[tenant_id][purpose], purpose=purpose) is None
        print("PASS: database revocation/consumption denies each signed token", flush=True)

        # Misconfigured credentials (without access to this DB role) fail closed.
        bad_engine, bad_factory = new_pool("mt_clone_a", "invalid-" + uuid4().hex)
        engines.append(bad_engine)
        bad_router = TenantCredentialLookup(keyring=keyring,
                                            sessions_by_tenant={tid_a: bad_factory})
        assert bad_router.lookup(issued[tid_a]["portal"], purpose="portal") is None
        print("PASS: invalid DB credentials do not trigger privileged fallback", flush=True)

        print("PASS: STAGE 19.18 ISOLATED SIGNED TENANT ROUTING AND DB HASH LOOKUP COMPLETED", flush=True)
        print("LIMITATION: production get_db / refresh / portal / consent endpoints do not use this resolver", flush=True)
    finally:
        for engine in engines:
            engine.dispose()


if __name__ == "__main__":
    main()
