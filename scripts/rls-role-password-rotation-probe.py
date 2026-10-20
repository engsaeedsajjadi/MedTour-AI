"""Stage 19.24 — credential rotation behind a central epoch fence (CLONE ONLY).

The Python process is a TEST HARNESS, not an HTTP worker. Only the harness
has mt_rotation_operator and mt_control_writer credentials. The app's staged
tenant-worker components receive neither one.

No production PostgreSQL, Compose volumes, real user data or migrations.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.models import Patient
from app.staged_tenant_epoch_control import PostgreSQLEpochReader, StagedCoordinatedTenantRegistry
from app.staged_tenant_pool_registry import TenantPrincipalConfig


def env(key: str) -> str:
    return os.environ["PROBE_" + key]


def make_engine(role: str, password: str):
    url = URL.create(
        "postgresql+psycopg",
        username=role, password=password,
        host="medtour-test-db", port=5432, database="medtour_principal_clone",
    )
    return create_engine(
        url, pool_size=2, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback",
        connect_args={"connect_timeout": 5},
    )


def config(letter: str, password: str):
    return TenantPrincipalConfig(
        tenant_id=env("TENANT_" + letter),
        slug="principal-poc-" + letter.lower(),
        whatsapp_phone_id="synthetic-phone-" + letter.lower(),
        database_role="mt_clone_" + letter.lower(),
        database_password=password,
        database_host="medtour-test-db",
        database_name="medtour_principal_clone",
    )


def verify_patient(lease, own: str, other: str, expected_role: str):
    with lease.session() as db:
        assert db.execute(text("SELECT session_user")).scalar_one() == expected_role
        rows = set(db.scalars(select(Patient.id)).all())
        assert own in rows and other not in rows


def deny(try_acquire, label):
    try:
        try_acquire()
    except LookupError:
        return
    raise AssertionError(f"{label}: a stale or disabled tenant acquired a lease")


def control_change(engine, tenant, current, enabled):
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE medtour_control.tenant_epochs "
                "SET generation=generation+1,enabled=:enabled "
                "WHERE tenant_id=:tenant AND generation=:current "
                "RETURNING generation"
            ),
            {"enabled": enabled, "tenant": tenant, "current": current},
        ).scalar_one()
    return result


def operator_rotate(engine, tenant, epoch, password):
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT medtour_control.rotate_synthetic_a(:tenant,:epoch,:password)"),
            {"tenant": tenant, "epoch": epoch, "password": password},
        ).scalar_one()


def expect_denied(action, label):
    try:
        action()
    except (DBAPIError, PermissionError):
        return
    raise AssertionError(f"{label}: operation should have been rejected")


def main():
    if (
        os.getenv("APP_ENV") != "test"
        or os.getenv("DATABASE_URL") != "sqlite://"
        or os.getenv("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Clone-only credential-rotation test guard failed")

    old_a = env("PASSWORD_A")
    new_a = env("NEW_PASSWORD_A")
    assert new_a != old_a and len(new_a) >= 40
    a, b = config("A", old_a), config("B", env("PASSWORD_B"))

    # Separate manager/operator credentials exist only in this test harness.
    readers = [
        make_engine("mt_control_reader", env("CONTROL_READ_PASSWORD")),
        make_engine("mt_control_reader", env("CONTROL_READ_PASSWORD")),
    ]
    writer = make_engine("mt_control_writer", env("CONTROL_WRITE_PASSWORD"))
    operator = make_engine("mt_rotation_operator", env("ROTATION_OPERATOR_PASSWORD"))
    workers = [
        StagedCoordinatedTenantRegistry(
            reader=PostgreSQLEpochReader(engine),
            max_tenants=2, pool_size=2,
        )
        for engine in readers
    ]
    held = None
    try:
        for worker in workers:
            worker.provision(a, generation=1)
            worker.provision(b, generation=1)
        for worker in workers:
            with worker.acquire_slug(a.slug) as lease:
                verify_patient(lease, env("PATIENT_A"), env("PATIENT_B"), "mt_clone_a")
            with worker.acquire_phone(b.whatsapp_phone_id) as lease:
                verify_patient(lease, env("PATIENT_B"), env("PATIENT_A"), "mt_clone_b")
        print("PASS: pre-rotation both tenants operate under RLS with independent worker pools", flush=True)

        expect_denied(
            lambda: operator_rotate(operator, b.tenant_id, 1, new_a),
            "Unauthorized tenant role rotation",
        )
        expect_denied(
            lambda: operator_rotate(operator, a.tenant_id, 1, new_a),
            "Password rotation before disabling tenant",
        )
        print("PASS: rotation operator cannot alter another tenant or rotate before epoch disable", flush=True)

        # Keep a physical SQL connection open, then prove it is terminated by
        # the privileged clone-only rotation operation.
        held = workers[0].acquire_tenant(a.tenant_id)
        held_context = held.session()
        open_session = held_context.__enter__()
        backend_pid = open_session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert isinstance(backend_pid, int)

        assert control_change(writer, a.tenant_id, 1, False) == 2
        for worker in workers:
            deny(lambda w=worker: w.acquire_tenant(a.tenant_id), "disabled tenant")
            with worker.acquire_tenant(b.tenant_id) as lease:
                verify_patient(lease, env("PATIENT_B"), env("PATIENT_A"), "mt_clone_b")
        assert workers[0].snapshot_counts()["draining_pools"] == 1
        print("PASS: disabled epoch blocks new Tenant A leases in both workers; B stays active", flush=True)

        # Only the isolated operator calls a fixed-SQL SECURITY DEFINER
        # function: no privileged credentials are passed to an API worker.
        killed = operator_rotate(operator, a.tenant_id, 2, new_a)
        assert killed >= 1, "Rotation failed to terminate the held old-credential session"
        print("PASS: password changed and at least one old authenticated SQL session terminated", flush=True)

        try:
            open_session.execute(text("SELECT 1")).scalar_one()
        except DBAPIError:
            pass
        else:
            raise AssertionError("Previously authenticated session survived forced disconnect")
        finally:
            # SQLAlchemy invalidates the interrupted connection; session and
            # lease must both be explicitly released before re-provisioning.
            try:
                held_context.__exit__(None, None, None)
            finally:
                held.close()
                held = None
        assert workers[0].snapshot_counts()["draining_pools"] == 0

        # SQLAlchemy's pre-existing pooled connections must not count as proof
        # of password invalidation: construct brand-new engines instead.
        old_probe = make_engine("mt_clone_a", old_a)
        new_probe = make_engine("mt_clone_a", new_a)
        try:
            expect_denied(
                lambda: old_probe.connect(),
                "Old password on a fresh TCP connection",
            )
            with new_probe.connect() as conn:
                assert conn.execute(text("SELECT session_user")).scalar_one() == "mt_clone_a"
        finally:
            old_probe.dispose()
            new_probe.dispose()
        print("PASS: old PostgreSQL credential rejected on fresh connection; new credential accepted", flush=True)

        expect_denied(
            lambda: operator_rotate(operator, a.tenant_id, 2, new_a),
            "Replay of an already-consumed rotation epoch",
        )
        for worker in workers:
            deny(lambda w=worker: w.acquire_tenant(a.tenant_id), "still disabled")
            with worker.acquire_tenant(b.tenant_id) as lease:
                verify_patient(lease, env("PATIENT_B"), env("PATIENT_A"), "mt_clone_b")
        print("PASS: rotation is one-time per epoch and Tenant B remains unaffected", flush=True)

        assert control_change(writer, a.tenant_id, 2, True) == 3
        for worker in workers:
            deny(lambda w=worker: w.acquire_tenant(a.tenant_id), "unprovisioned epoch")
            try:
                worker.provision(a, generation=1)
            except LookupError:
                pass
            else:
                raise AssertionError("Old generation was accepted after credential cutover")
            worker.provision(config("A", new_a), generation=3)
            with worker.acquire_tenant(a.tenant_id) as lease:
                verify_patient(lease, env("PATIENT_A"), env("PATIENT_B"), "mt_clone_a")
            with worker.acquire_tenant(b.tenant_id) as lease:
                verify_patient(lease, env("PATIENT_B"), env("PATIENT_A"), "mt_clone_b")
        print("PASS: both workers recover with the new secret at epoch 3 under RLS", flush=True)

        # A privileged rollback of just the *generation* must not be allowed.
        expect_denied(
            lambda: control_change(writer, a.tenant_id, 1, True),
            "Control epoch rollback",
        )
        print("PASS: old epoch cannot be replayed to reopen stale workers", flush=True)
        print("PASS: STAGE 19.24 ISOLATED TENANT POSTGRESQL CREDENTIAL ROTATION TEST COMPLETED", flush=True)
        print("LIMITATION: clone-only operator; real Secret Manager, cross-process rollout and API routing are not migrated", flush=True)
    finally:
        if held is not None:
            # Last-resort cleanup on assertion errors; never leave lease behind.
            try:
                held.close()
            except RuntimeError:
                pass
        for worker in workers:
            worker.close()
        for engine in readers:
            engine.dispose()
        writer.dispose()
        operator.dispose()


if __name__ == "__main__":
    main()
