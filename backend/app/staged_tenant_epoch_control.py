"""Stage 19.23: per-request PostgreSQL epoch verification across independent workers.

STAGED ONLY. Nothing in main.py/get_db imports this module. A shared, narrowly
readable tenant-generation table acts as the distributed cutover barrier.

Each *new* lease requires an uncached read. If the central read fails, access
is denied without any fallback to the old local registry or privileged DB.
After a revoked/changed epoch is detected, the worker retires its old local
pool. Already-open leases are allowed to drain: this design does not promise
immediate cancellation of already-started requests, and a race between the
last control-plane read and a central update remains possible.

Generation replacement gates staged credential rotation, but does not rotate
or invalidate PostgreSQL passwords itself; an authorized, separate control
plane must provision new roles and revoke old DB credentials.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .staged_tenant_pool_registry import StagedTenantPoolRegistry, TenantPrincipalConfig


@dataclass(frozen=True)
class EpochState:
    generation: int
    enabled: bool

    def __post_init__(self):
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("Invalid central tenant epoch")
        if type(self.enabled) is not bool:
            raise ValueError("Invalid tenant enabled flag")


class EpochReader(Protocol):
    def read(self, tenant_id: str) -> EpochState | None: ...


class PostgreSQLEpochReader:
    """Select-only, authenticated DB-login reader for an external control plane.

    Engine must be provisioned with a distinct mt_control_reader credential;
    it must NOT connect as the database owner or tenant application role.
    """

    def __init__(self, engine: Engine, *, expected_role: str = "mt_control_reader"):
        if not isinstance(expected_role, str) or not expected_role:
            raise ValueError("Expected explicit control reader login")
        self._engine = engine
        self._expected_role = expected_role

    def read(self, tenant_id: str) -> EpochState | None:
        # An exception is NOT a missing row: callers fail closed on ALL faults.
        with self._engine.connect() as conn:
            role = conn.execute(text(
                "SELECT current_user::text, session_user::text, "
                "r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb, "
                "r.rolreplication, "
                "has_table_privilege('public.patients','SELECT'), "
                "has_table_privilege('public.tenants','SELECT'), "
                "has_table_privilege('medtour_control.tenant_epochs','UPDATE') "
                "FROM pg_roles r WHERE r.rolname=session_user"
            )).one()
            if (
                role[0] != self._expected_role
                or role[1] != self._expected_role
                or any(role[2:])
            ):
                raise PermissionError("Control reader has wrong PostgreSQL principal or privileges")
            result = conn.execute(text(
                "SELECT generation, enabled FROM medtour_control.tenant_epochs "
                "WHERE tenant_id=:tenant_id"
            ), {"tenant_id": tenant_id}).one_or_none()
            if result is None:
                return None
            return EpochState(generation=result[0], enabled=result[1])


class StagedCoordinatedTenantRegistry:
    """One instance per worker; shared epoch store, independent local pools.

    This wrapper owns its local StagedTenantPoolRegistry. It must be the ONLY
    route to acquiring leases in that worker: direct access to its private
    local registry would bypass cross-worker epoch checks.
    """

    def __init__(
        self, *, reader: EpochReader, max_tenants: int = 8,
        pool_size: int = 2, engine_builder=None,
    ):
        if reader is None or not callable(getattr(reader, "read", None)):
            raise ValueError("An authenticated central epoch reader is required")
        self._reader = reader
        args = {"max_tenants": max_tenants, "pool_size": pool_size}
        if engine_builder is not None:
            args["engine_builder"] = engine_builder
        self._local = StagedTenantPoolRegistry(**args)
        self._generations: dict[str, int] = {}
        self._slugs: dict[str, str] = {}
        self._phones: dict[str, str] = {}
        self._lock = threading.RLock()
        self._closed = False

    def _state(self, tid: str) -> EpochState | None:
        try:
            state = self._reader.read(tid)
        except Exception as exc:
            raise LookupError("Central tenant control plane unavailable") from exc
        if state is not None and not isinstance(state, EpochState):
            raise LookupError("Central tenant control plane returned invalid state")
        return state

    def _retire_locked(self, tid: str):
        if tid not in self._generations:
            return
        self._generations.pop(tid)
        for dictionary in (self._slugs, self._phones):
            for key, value in list(dictionary.items()):
                if value == tid:
                    dictionary.pop(key, None)
        self._local.revoke(tid)

    def provision(self, config: TenantPrincipalConfig, *, generation: int):
        """Accept an explicit trusted provision only for the current epoch.

        Epoch increments intentionally require replacing the old pool and
        (typically) using a new uniquely provisioned DB login role.
        """
        if not isinstance(config, TenantPrincipalConfig):
            raise ValueError("Expected trusted TenantPrincipalConfig")
        if type(generation) is not int or generation < 1:
            raise ValueError("Invalid trusted generation")
        with self._lock:
            if self._closed:
                raise RuntimeError("Registry has been shut down")
            current = self._state(config.tenant_id)
            if current != EpochState(generation, True):
                self._retire_locked(config.tenant_id)
                raise LookupError("Tenant is disabled or has stale provisioning epoch")
            if config.tenant_id in self._generations:
                raise ValueError("Tenant is already provisioned in this worker")
            if config.slug in self._slugs or config.whatsapp_phone_id in self._phones:
                raise ValueError("Tenant registry alias is already reserved")
            self._local.enroll(config)
            try:
                # Check again because connection validation can take time.
                if self._state(config.tenant_id) != current:
                    raise LookupError("Tenant epoch changed during provisioning")
            except Exception:
                self._local.revoke(config.tenant_id)
                raise
            self._generations[config.tenant_id] = generation
            self._slugs[config.slug] = config.tenant_id
            self._phones[config.whatsapp_phone_id] = config.tenant_id

    def _acquire(self, tid: str):
        with self._lock:
            if self._closed or tid not in self._generations:
                raise LookupError("Tenant is not registered in this worker")
            current = self._state(tid)
            if current != EpochState(self._generations[tid], True):
                self._retire_locked(tid)
                raise LookupError("Tenant was revoked or credential generation changed")
            return self._local.acquire_tenant(tid)

    def acquire_tenant(self, tenant_id: str):
        return self._acquire(tenant_id)

    def acquire_slug(self, slug: str):
        with self._lock:
            tid = self._slugs.get(slug)
            if tid is None:
                raise LookupError("Tenant slug is not registered")
            return self._acquire(tid)

    def acquire_phone(self, phone_id: str):
        with self._lock:
            tid = self._phones.get(phone_id)
            if tid is None:
                raise LookupError("Meta account is not registered")
            return self._acquire(tid)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generations.clear()
            self._slugs.clear()
            self._phones.clear()
            self._local.close()

    def snapshot_counts(self):
        with self._lock:
            return self._local.snapshot_counts()
