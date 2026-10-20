"""Stage 19.23 distributed epoch revocation with two independent workers.

Only on a synthetic, restored PostgreSQL clone. The test harness possesses a
separate limited writer credential to simulate the control-plane service;
an HTTP worker must NEVER be given that writer credential in production.
"""
from __future__ import annotations

import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.staged_tenant_epoch_control import (
    EpochState, PostgreSQLEpochReader, StagedCoordinatedTenantRegistry,
)
from app.staged_tenant_pool_registry import TenantPrincipalConfig
from app.models import Patient
from sqlalchemy import select


def e(name: str) -> str:
    return os.environ["PROBE_" + name]


def engine_for(role: str, password: str, size: int = 1):
    url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host="medtour-test-db", port=5432, database="medtour_principal_clone",
    )
    return create_engine(
        url, pool_size=size, max_overflow=0, pool_pre_ping=True,
        pool_reset_on_return="rollback", connect_args={"connect_timeout": 5},
    )


def config(suffix):
    return TenantPrincipalConfig(
        tenant_id=e("TENANT_" + suffix),
        slug="principal-poc-" + suffix.lower(),
        whatsapp_phone_id="synthetic-phone-" + suffix.lower(),
        database_role="mt_clone_" + suffix.lower(),
        database_password=e("PASSWORD_" + suffix),
        database_host="medtour-test-db",
        database_name="medtour_principal_clone",
    )


def own_patient(lease, tid, patient_id, foreign_id):
    with lease.session() as db:
        ids = set(db.scalars(select(Patient.id)).all())
        assert patient_id in ids and foreign_id not in ids
        principal = db.execute(text("SELECT session_user")).scalar_one()
        return principal


def denied(action):
    try:
        action()
    except LookupError:
        return
    raise AssertionError("Central tenant epoch check should have blocked the request")


def advance(writer, tid: str, expected: int, *, enabled: bool):
    with writer.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE medtour_control.tenant_epochs "
                "SET generation=generation+1, enabled=:enabled "
                "WHERE tenant_id=:tid AND generation=:expected "
                "RETURNING generation"
            ),
            {"tid": tid, "expected": expected, "enabled": enabled},
        ).scalar_one()
    return result


def main():
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DATABASE_URL") != "sqlite://"
        or os.environ.get("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Stage 19.23 must run in a synthetic isolated clone")
    a, b = config("A"), config("B")
    ctrl_a = engine_for("mt_control_reader", e("CONTROL_READ_PASSWORD"))
    ctrl_b = engine_for("mt_control_reader", e("CONTROL_READ_PASSWORD"))
    writer = engine_for("mt_control_writer", e("CONTROL_WRITE_PASSWORD"))
    worker_a = StagedCoordinatedTenantRegistry(
        reader=PostgreSQLEpochReader(ctrl_a), max_tenants=2, pool_size=2,
    )
    worker_b = StagedCoordinatedTenantRegistry(
        reader=PostgreSQLEpochReader(ctrl_b), max_tenants=2, pool_size=2,
    )
    try:
        with ctrl_a.connect() as conn:
            who = conn.execute(text("SELECT session_user")).scalar_one()
            assert who == "mt_control_reader"
            for forbidden in ("SELECT count(*) FROM public.patients",
                              "UPDATE medtour_control.tenant_epochs SET enabled=true"):
                try:
                    conn.execute(text(forbidden))
                except DBAPIError as exc:
                    assert getattr(exc.orig, "sqlstate", None) == "42501"
                    conn.rollback()
                else:
                    raise AssertionError("Read-only control role has write/PHI access")
        with writer.connect() as conn:
            assert conn.execute(text("SELECT session_user")).scalar_one() == "mt_control_writer"
            try:
                conn.execute(text("SELECT count(*) FROM public.patients"))
            except DBAPIError as exc:
                assert getattr(exc.orig, "sqlstate", None) == "42501"
                conn.rollback()
            else:
                raise AssertionError("Control writer unexpectedly reads PHI")
        print("PASS: reader and writer control roles cannot access patient records", flush=True)

        for worker in (worker_a, worker_b):
            worker.provision(a, generation=1)
            worker.provision(b, generation=1)
        # Keep a request that was authenticated BEFORE the remote disable.
        outstanding = worker_a.acquire_tenant(a.tenant_id)
        with worker_a.acquire_slug(b.slug) as lease:
            assert own_patient(
                lease, b.tenant_id, e("PATIENT_B"), e("PATIENT_A")
            ) == b.database_role
        print("PASS: two independent worker registries enrolled by authenticated epoch", flush=True)

        assert advance(writer, a.tenant_id, 1, enabled=False) == 2
        for worker in (worker_a, worker_b):
            denied(lambda w=worker: w.acquire_tenant(a.tenant_id))
            denied(lambda w=worker: w.acquire_slug(a.slug))
            with worker.acquire_phone(b.whatsapp_phone_id) as lease:
                assert own_patient(
                    lease, b.tenant_id, e("PATIENT_B"), e("PATIENT_A")
                ) == b.database_role
        assert worker_a.snapshot_counts()["draining_pools"] == 1
        assert worker_b.snapshot_counts()["tenants"] == 1
        print("PASS: centralized disable revokes new Tenant A leases in BOTH workers", flush=True)

        # Established in-flight connection is explicitly allowed to drain.
        assert own_patient(
            outstanding, a.tenant_id, e("PATIENT_A"), e("PATIENT_B")
        ) == a.database_role
        outstanding.close()
        assert worker_a.snapshot_counts()["draining_pools"] == 0
        print("PASS: in-flight lease drains and retiring pool is released", flush=True)

        # Re-enable with a *higher* generation. Old-generation workers MUST
        # explicitly reprovision before taking any new requests.
        assert advance(writer, a.tenant_id, 2, enabled=True) == 3
        for worker in (worker_a, worker_b):
            denied(lambda w=worker: w.acquire_tenant(a.tenant_id))
            try:
                worker.provision(a, generation=1)
            except LookupError:
                pass
            else:
                raise AssertionError("Stale generation enrolled")
            worker.provision(a, generation=3)
            with worker.acquire_tenant(a.tenant_id) as lease:
                assert own_patient(
                    lease, a.tenant_id, e("PATIENT_A"), e("PATIENT_B")
                ) == a.database_role
        print("PASS: epoch increment fences stale workers until trusted reprovisioning", flush=True)

        # A compromised/buggy control writer cannot roll generation backwards.
        try:
            with writer.begin() as conn:
                conn.execute(text(
                    "UPDATE medtour_control.tenant_epochs SET generation=1 "
                    "WHERE tenant_id=:tid"
                ), {"tid": a.tenant_id})
        except DBAPIError:
            pass
        else:
            raise AssertionError("Control generation rollback unexpectedly succeeded")
        reader = PostgreSQLEpochReader(ctrl_a)
        assert reader.read(a.tenant_id) == EpochState(3, True)
        print("PASS: monotonic SQL control prevents generation rollback", flush=True)
        print("PASS: STAGE 19.23 ISOLATED MULTIWORKER TENANT EPOCH REVOCATION TEST COMPLETED", flush=True)
        print("LIMITATION: this does not rotate DB passwords, terminate existing in-flight SQL, or migrate production get_db", flush=True)
    finally:
        outstanding_close = locals().get("outstanding")
        if outstanding_close is not None:
            outstanding_close.close()
        worker_a.close()
        worker_b.close()
        ctrl_a.dispose()
        ctrl_b.dispose()
        writer.dispose()


if __name__ == "__main__":
    main()
