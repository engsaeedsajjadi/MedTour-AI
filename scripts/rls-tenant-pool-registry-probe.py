"""Stage 19.22: bounded tenant LOGIN pool lifecycle over real clone PostgreSQL.

This test runs only inside the disposable internal Docker network. It does not
provision, revoke or migrate any role/database in the user's live services.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os

from sqlalchemy import select, text

from app.models import Patient
from app.staged_tenant_pool_registry import (
    StagedTenantPoolRegistry,
    TenantPrincipalConfig,
)


def e(name: str) -> str:
    return os.environ["PROBE_" + name]


def configuration(index: int):
    suffix = "A" if index == 0 else "B"
    return TenantPrincipalConfig(
        tenant_id=e("TENANT_" + suffix),
        slug="principal-poc-" + suffix.lower(),
        whatsapp_phone_id="synthetic-phone-" + suffix.lower(),
        database_role="mt_clone_" + suffix.lower(),
        database_password=e("PASSWORD_" + suffix),
        database_host="medtour-test-db",
        database_name="medtour_principal_clone",
    )


def row_check(lease, tid: str, own_id: str, other_id: str):
    with lease.session() as db:
        identity = db.execute(
            text("SELECT session_user, medtour_principal_private.tenant_for_login()")
        ).one()
        assert identity[1] == tid
        rows = set(db.scalars(select(Patient.id)).all())
        assert own_id in rows
        assert other_id not in rows
        return str(identity[0])


def main():
    if (
        os.getenv("APP_ENV") != "test"
        or os.getenv("DATABASE_URL") != "sqlite://"
        or os.getenv("PROBE_DB_HOST") != "medtour-test-db"
    ):
        raise RuntimeError("Stage 19.22 registry test must run on disposable clone")
    reg = StagedTenantPoolRegistry(max_tenants=2, pool_size=2)
    a, b = configuration(0), configuration(1)
    try:
        reg.enroll(a)
        reg.enroll(b)
        assert reg.snapshot_counts()["connections_budget"] == 4
        print("PASS: bounded pools accepted two verified low-privilege PostgreSQL LOGINs", flush=True)

        for own, other, own_id, other_id in (
            (a, b, e("PATIENT_A"), e("PATIENT_B")),
            (b, a, e("PATIENT_B"), e("PATIENT_A")),
        ):
            with reg.acquire_slug(own.slug) as lease:
                assert lease.tenant_id == own.tenant_id
                assert row_check(lease, own.tenant_id, own_id, other_id) == own.database_role
            with reg.acquire_phone(own.whatsapp_phone_id) as lease:
                assert row_check(lease, own.tenant_id, own_id, other_id) == own.database_role
        print("PASS: slug, Meta account and tenant registry leases preserve RLS isolation", flush=True)

        with ThreadPoolExecutor(max_workers=4) as tasks:
            checks = [
                tasks.submit(_thread_row_check, reg, c, e("PATIENT_A") if i == 0 else e("PATIENT_B"),
                             e("PATIENT_B") if i == 0 else e("PATIENT_A"))
                for i, c in enumerate((a, b)) for _ in range(4)
            ]
            assert all(f.result() for f in checks)
        assert reg.snapshot_counts()["active_leases"] == 0
        print("PASS: concurrent per-tenant leases return without pool identity bleed", flush=True)

        # Misconfigured trusted role-to-tenant pair must fail enrollment before
        # any session is made visible to HTTP routing.
        misconfigured = StagedTenantPoolRegistry(max_tenants=1, pool_size=1)
        try:
            wrong = TenantPrincipalConfig(
                tenant_id=b.tenant_id,
                slug="incorrect-pair",
                whatsapp_phone_id="incorrect-wa",
                database_role=a.database_role,
                database_password=a.database_password,
            )
            try:
                misconfigured.enroll(wrong)
            except PermissionError:
                pass
            else:
                raise AssertionError("Wrong role/tenant mapping was enrolled")
            assert misconfigured.snapshot_counts()["tenants"] == 0
        finally:
            misconfigured.close()
        print("PASS: wrong trusted tenant-to-login mapping fails before pool publication", flush=True)

        # Revoke while one already-authenticated request has a live lease.
        outstanding = reg.acquire_tenant(a.tenant_id)
        reg.revoke(a.tenant_id)
        status = reg.snapshot_counts()
        assert status["tenants"] == 1
        assert status["draining_pools"] == 1
        assert status["active_leases"] == 1
        for method, selector in (
            (reg.acquire_tenant, a.tenant_id),
            (reg.acquire_slug, a.slug),
            (reg.acquire_phone, a.whatsapp_phone_id),
        ):
            try:
                method(selector)
            except LookupError:
                pass
            else:
                raise AssertionError("Revoked tenant accepted a new lease")
        # Existing in-flight request is allowed to complete under its pinned DB
        # principal. Revocation does not instantaneously terminate active SQL.
        assert row_check(outstanding, a.tenant_id, e("PATIENT_A"), e("PATIENT_B")) == a.database_role
        outstanding.close()
        assert reg.snapshot_counts()["draining_pools"] == 0
        try:
            with outstanding.session():
                pass
        except RuntimeError:
            pass
        else:
            raise AssertionError("Revoked and released lease opened another DB session")
        with reg.acquire_slug(b.slug) as still_active:
            assert row_check(still_active.factory, b.tenant_id, e("PATIENT_B"), e("PATIENT_A")) == b.database_role
        print("PASS: tenant revocation blocks new leases, drains active work and preserves other tenant", flush=True)

        reg.close()
        assert reg.snapshot_counts()["closed"] is True
        try:
            reg.acquire_tenant(b.tenant_id)
        except LookupError:
            pass
        else:
            raise AssertionError("Closed registry opened a tenant pool")
        print("PASS: registry shutdown denies fresh requests and disposes idle pools", flush=True)
        print("PASS: STAGE 19.22 ISOLATED TENANT POOL REGISTRY LIFECYCLE TEST COMPLETED", flush=True)
        print("LIMITATION: in-process registry only; no multi-worker revocation, secret rotation or live API wiring", flush=True)
    finally:
        reg.close()


def _thread_row_check(reg, config, own_id, foreign_id):
    with reg.acquire_tenant(config.tenant_id) as lease:
        return row_check(lease, config.tenant_id, own_id, foreign_id) == config.database_role


if __name__ == "__main__":
    main()
