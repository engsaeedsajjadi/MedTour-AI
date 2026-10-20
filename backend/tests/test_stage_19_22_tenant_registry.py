"""Stage 19.22 — offline verification of bounded tenant pool registry."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

from app.staged_tenant_pool_registry import (
    StagedTenantPoolRegistry,
    TenantPrincipalConfig,
)

TID_A = "11111111-1111-4111-8111-111111111111"
TID_B = "22222222-2222-4222-8222-222222222222"
ROLE_MAP = {"mt_clone_a": TID_A, "mt_clone_b": TID_B}


class FakeResult:
    def __init__(self, row):
        self.row = row

    def one(self):
        return self.row


class FakeConnection:
    def __init__(self, fake_engine):
        self.engine = fake_engine

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        if "medtour_principal_private.tenant_for_login()" not in str(statement):
            raise AssertionError("Missing authenticated principal verification")
        role = self.engine.url.username
        tid = self.engine.role_map.get(role)
        flags = self.engine.flags
        return FakeResult((role, role, tid, *flags))


class FakeEngine:
    def __init__(self, url, *, role_map=None, flags=(False,)*6):
        self.url = url
        self.role_map = role_map or ROLE_MAP
        self.flags = flags
        self.disposals = 0

    def connect(self):
        return FakeConnection(self)

    def dispose(self):
        self.disposals += 1


class FakeBuilder:
    def __init__(self, *, role_map=None, flags=(False,)*6):
        self.engines = []
        self.options = []
        self.role_map = role_map
        self.flags = flags

    def __call__(self, url, **options):
        self.options.append(options)
        engine = FakeEngine(url, role_map=self.role_map, flags=self.flags)
        self.engines.append(engine)
        return engine


def config(tid=TID_A, slug="principal-a", phone="wa-a", role="mt_clone_a"):
    return TenantPrincipalConfig(
        tenant_id=tid, slug=slug, whatsapp_phone_id=phone,
        database_role=role, database_password="synthetic-password-" + "x"*48
    )


def registry(builder=None, *, max_tenants=2, pool_size=2):
    builder = builder or FakeBuilder()
    return StagedTenantPoolRegistry(
        engine_builder=builder, max_tenants=max_tenants, pool_size=pool_size
    ), builder


def test_bounded_enrollment_and_all_three_lookup_methods():
    reg, fake = registry()
    reg.enroll(config())
    reg.enroll(config(TID_B, "principal-b", "wa-b", "mt_clone_b"))
    with reg.acquire_slug("principal-a") as lease:
        assert lease.tenant_id == TID_A
        assert lease.factory is not None
    with reg.acquire_phone("wa-b") as lease:
        assert lease.tenant_id == TID_B
    with reg.acquire_tenant(TID_B) as lease:
        assert lease.tenant_id == TID_B
    assert reg.snapshot_counts() == {
        "tenants": 2, "active_leases": 0, "max_tenants": 2,
        "connections_budget": 4, "draining_pools": 0, "closed": False,
    }
    for opts in fake.options:
        assert opts["pool_size"] == 2
        assert opts["max_overflow"] == 0
        assert opts["pool_timeout"] == 5
        assert opts["pool_pre_ping"] is True
        assert opts["pool_reset_on_return"] == "rollback"
        assert opts["connect_args"]["connect_timeout"] == 5
    reg.close()
    assert all(e.disposals == 1 for e in fake.engines)


def test_duplicate_slug_phone_and_shared_login_are_rejected_without_new_engine():
    reg, fake = registry()
    reg.enroll(config())
    bad = [
        config(TID_B, "principal-b", "wa-b", "mt_clone_a"),
        config(TID_B, "principal-a", "wa-b", "mt_clone_b"),
        config(TID_B, "principal-b", "wa-a", "mt_clone_b"),
        config(TID_A, "principal-b", "wa-b", "mt_clone_b"),
    ]
    for item in bad:
        with pytest.raises(ValueError):
            reg.enroll(item)
    assert len(fake.engines) == 1
    reg.close()


def test_capacity_denies_additional_connection_pool():
    reg, fake = registry(max_tenants=1)
    reg.enroll(config())
    with pytest.raises(ValueError, match="capacity"):
        reg.enroll(config(TID_B, "principal-b", "wa-b", "mt_clone_b"))
    assert len(fake.engines) == 1
    reg.close()


@pytest.mark.parametrize("wrong", [
    config(TID_A, "principal-a", "wa-a", "mt_clone_b"),
    config(TID_A, "principal-a", "wa-a", "mt_clone_a"),
])
def test_wrong_tenant_role_or_escalated_permissions_fails_before_registration(wrong):
    role_map = {"mt_clone_a": TID_B, "mt_clone_b": TID_B}
    fake = FakeBuilder(role_map=role_map)
    reg, _ = registry(fake)
    with pytest.raises(PermissionError):
        reg.enroll(wrong if wrong.database_role == "mt_clone_a" else replace(wrong, tenant_id=TID_A))
    assert fake.engines[-1].disposals == 1
    assert reg.snapshot_counts()["tenants"] == 0


def test_privileged_login_is_denied_and_engine_disposed():
    fake = FakeBuilder(flags=(True,False,False,False,False,False))
    reg, _ = registry(fake)
    with pytest.raises(PermissionError):
        reg.enroll(config())
    assert fake.engines[0].disposals == 1


def test_revocation_denies_new_leases_while_active_lease_drains():
    reg, fake = registry()
    reg.enroll(config())
    lease = reg.acquire_tenant(TID_A)
    assert lease.tenant_id == TID_A
    reg.revoke(TID_A)
    assert reg.snapshot_counts()["tenants"] == 0
    assert reg.snapshot_counts()["active_leases"] == 1
    assert reg.snapshot_counts()["draining_pools"] == 1
    assert fake.engines[0].disposals == 0
    for selector, arg in (
        (reg.acquire_tenant, TID_A),
        (reg.acquire_slug, "principal-a"),
        (reg.acquire_phone, "wa-a"),
    ):
        with pytest.raises(LookupError):
            selector(arg)
    with pytest.raises(ValueError):
        reg.enroll(config(TID_B, "principal-b", "wa-b", "mt_clone_a"))
    lease.close()
    lease.close()
    assert fake.engines[0].disposals == 1
    assert reg.snapshot_counts()["active_leases"] == 0
    assert reg.snapshot_counts()["draining_pools"] == 0
    with pytest.raises(RuntimeError):
        _ = lease.factory
    reg.close()


def test_close_during_active_lease_does_not_dispose_until_release():
    reg, fake = registry()
    reg.enroll(config())
    with reg.acquire_tenant(TID_A) as lease:
        reg.close()
        assert reg.snapshot_counts()["closed"] is True
        assert fake.engines[0].disposals == 0
        with pytest.raises(LookupError):
            reg.acquire_tenant(TID_A)
        with pytest.raises(RuntimeError):
            reg.enroll(config(TID_B, "principal-b", "wa-b", "mt_clone_b"))
        assert lease.factory is not None
    assert fake.engines[0].disposals == 1
    reg.close()


def test_multiple_concurrent_leases_are_drained_before_disposal():
    reg, fake = registry()
    reg.enroll(config())

    def worker(_):
        with reg.acquire_slug("principal-a") as lease:
            return lease.tenant_id

    with ThreadPoolExecutor(max_workers=6) as executor:
        assert list(executor.map(worker, range(40))) == [TID_A]*40
    assert reg.snapshot_counts()["active_leases"] == 0
    reg.revoke(TID_A)
    assert fake.engines[0].disposals == 1


def test_invalid_registry_limits_and_configs_rejected():
    for lim, size in ((17, 1), (0, 1), (8, 5), (16, 4), (True, 2)):
        with pytest.raises(ValueError):
            registry(max_tenants=lim, pool_size=size)
    with pytest.raises(ValueError):
        config("invalid-id")
    with pytest.raises(ValueError):
        config(role="postgres")
    with pytest.raises(ValueError):
        config(slug="INVALID!")
    with pytest.raises(ValueError):
        config(phone="invalid phone")
    with pytest.raises(ValueError):
        replace(config(), database_password="short")
    with pytest.raises(ValueError):
        replace(config(), database_port=True)


def test_password_never_appears_in_configuration_repr_or_registry_metrics():
    item = config()
    assert item.database_password not in repr(item)
    reg, fake = registry()
    reg.enroll(item)
    with reg.acquire_slug(item.slug) as lease:
        assert item.database_password not in repr(lease)
    assert item.database_password not in repr(reg.snapshot_counts())
    reg.close()
