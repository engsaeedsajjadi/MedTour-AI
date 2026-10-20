"""Stage 19.23: two independent workers share a central epoch authority.

Unit checks use synthetic in-memory epoch states and fake SQLAlchemy engines.
The PostgreSQL integration test separately validates real reader/writer roles.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.staged_tenant_epoch_control import (
    EpochState, PostgreSQLEpochReader, StagedCoordinatedTenantRegistry,
)
from test_stage_19_22_tenant_registry import FakeBuilder, config, TID_A, TID_B


class SharedEpochReader:
    def __init__(self):
        self.states = {TID_A: EpochState(1, True), TID_B: EpochState(1, True)}
        self.broken = False
        self.calls = 0

    def read(self, tid):
        self.calls += 1
        if self.broken:
            raise ConnectionError("Synthetic control database offline")
        return self.states.get(tid)


def worker(reader):
    fake = FakeBuilder()
    return StagedCoordinatedTenantRegistry(
        reader=reader, max_tenants=2, pool_size=2, engine_builder=fake
    ), fake


def test_two_workers_revoke_same_tenant_on_next_uncached_read():
    authority = SharedEpochReader()
    a, engines_a = worker(authority)
    b, engines_b = worker(authority)
    try:
        a.provision(config(), generation=1)
        b.provision(config(), generation=1)
        with a.acquire_tenant(TID_A) as first, b.acquire_slug("principal-a") as second:
            assert first.tenant_id == second.tenant_id == TID_A
            reads_before = authority.calls
            authority.states[TID_A] = EpochState(2, False)
            with pytest.raises(LookupError, match="revoked|epoch"):
                a.acquire_tenant(TID_A)
            with pytest.raises(LookupError, match="revoked|epoch"):
                b.acquire_slug("principal-a")
            assert authority.calls >= reads_before + 2
            assert a.snapshot_counts()["draining_pools"] == 1
            assert b.snapshot_counts()["draining_pools"] == 1
            with first.session() as db:
                assert db is not None  # in-flight work can drain
        assert a.snapshot_counts()["draining_pools"] == 0
        assert b.snapshot_counts()["draining_pools"] == 0
        assert engines_a.engines[0].disposals == 1
        assert engines_b.engines[0].disposals == 1
    finally:
        a.close()
        b.close()


def test_control_plane_outage_fails_closed_on_every_worker():
    authority = SharedEpochReader()
    a, _ = worker(authority)
    b, _ = worker(authority)
    try:
        a.provision(config(), generation=1)
        b.provision(config(), generation=1)
        authority.broken = True
        for registry in (a, b):
            with pytest.raises(LookupError, match="unavailable"):
                registry.acquire_tenant(TID_A)
            with pytest.raises(LookupError, match="unavailable"):
                registry.acquire_slug("principal-a")
        authority.broken = False
        with a.acquire_tenant(TID_A):
            pass
        with b.acquire_phone("wa-a"):
            pass
    finally:
        a.close()
        b.close()


def test_generation_change_requires_new_trusted_provision():
    authority = SharedEpochReader()
    a, fake = worker(authority)
    try:
        a.provision(config(), generation=1)
        authority.states[TID_A] = EpochState(2, True)
        with pytest.raises(LookupError, match="revoked|generation"):
            a.acquire_tenant(TID_A)
        with pytest.raises(LookupError):
            a.provision(config(), generation=1)
        a.provision(config(), generation=2)
        with a.acquire_tenant(TID_A) as lease:
            assert lease.tenant_id == TID_A
        assert len(fake.engines) == 2
        assert fake.engines[0].disposals == 1
    finally:
        a.close()


def test_other_tenant_stays_available_after_disable():
    authority = SharedEpochReader()
    a, fake = worker(authority)
    try:
        a.provision(config(), generation=1)
        a.provision(config(TID_B, "principal-b", "wa-b", "mt_clone_b"), generation=1)
        authority.states[TID_A] = EpochState(2, False)
        with pytest.raises(LookupError):
            a.acquire_slug("principal-a")
        with a.acquire_phone("wa-b") as lease:
            assert lease.tenant_id == TID_B
        assert a.snapshot_counts()["tenants"] == 1
    finally:
        a.close()


def test_central_epoch_cannot_be_bool_or_zero():
    for generation in (0, -1, True, "1"):
        with pytest.raises(ValueError):
            EpochState(generation, True)
    with pytest.raises(ValueError):
        EpochState(1, "true")


def test_untrusted_reader_result_fails_closed():
    class BadReader:
        def read(self, tid):
            return (1, True)  # wrong schema, no implicit truthiness

    a, fake = worker(BadReader())
    with pytest.raises(LookupError, match="invalid state"):
        a.provision(config(), generation=1)
    assert fake.engines == []
    a.close()


def test_control_epoch_must_be_present_before_connecting_to_tenant_db():
    authority = SharedEpochReader()
    authority.states.clear()
    a, fake = worker(authority)
    try:
        with pytest.raises(LookupError):
            a.provision(config(), generation=1)
        assert len(fake.engines) == 0
    finally:
        a.close()


def test_control_unavailability_during_enrollment_never_publishes_pool():
    authority = SharedEpochReader()
    a, fake = worker(authority)
    first_read = authority.read

    def fail_second(tid):
        if authority.calls >= 1:
            raise ConnectionError("Control disappeared during DB principal verification")
        return first_read(tid)

    authority.read = fail_second
    try:
        with pytest.raises(LookupError):
            a.provision(config(), generation=1)
        assert len(fake.engines) == 1
        assert fake.engines[0].disposals == 1
        assert a.snapshot_counts()["tenants"] == 0
    finally:
        a.close()


def test_reader_permission_assertions_are_not_silently_ignored():
    class Result:
        def __init__(self, row):
            self.row = row

        def one(self):
            return self.row

    class Conn:
        def __init__(self, privileged):
            self.privileged = privileged

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, statement, bindings=None):
            query = str(statement)
            if "FROM pg_roles" in query:
                return Result(("mt_control_reader", "mt_control_reader",
                               False, self.privileged, False, False, False,
                               False, False, False))
            raise AssertionError("Privileged fake role may not query epoch data")

    class Engine:
        def __init__(self, privileged):
            self.privileged = privileged

        def connect(self):
            return Conn(self.privileged)

    with pytest.raises(PermissionError):
        PostgreSQLEpochReader(Engine(True)).read(TID_A)
