"""Stage 19.22 — bounded, verified PostgreSQL tenant principal registry.

STAGED ONLY: NOT wired to the live FastAPI get_db, webhook or migration process.

Only trusted server-side provisioning is allowed. Every new engine is checked
against PostgreSQL's authenticated LOGIN principal, protected tenant mapping,
and non-privileged role attributes BEFORE it is registered. HTTP-supplied
tenant IDs, credentials or connection strings must never be used to enroll.

A registry lease pins an engine while a request is active. Revocation blocks
new leases immediately and disposes the engine after the final lease ends.
This is LOCAL PROCESS revocation only: in a multi-worker deployment, a
cross-worker control plane, secret rotation and DB-side role termination are
still required. Closing a pool does NOT invalidate previously issued tokens.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import sessionmaker

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,99}\Z")
_PROVIDER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_ROLE = re.compile(r"[a-z][a-z0-9_]{2,62}\Z")
_FORBIDDEN_ROLES = frozenset({"postgres", "medtour", "admin", "root", "superuser"})


@dataclass(frozen=True)
class TenantPrincipalConfig:
    tenant_id: str
    slug: str
    whatsapp_phone_id: str
    database_role: str
    database_password: str = field(repr=False)
    database_host: str = "medtour-test-db"
    database_name: str = "medtour_principal_clone"
    database_port: int = 5432

    def __post_init__(self):
        try:
            canonical = str(UUID(self.tenant_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("Invalid tenant UUID") from exc
        if canonical != self.tenant_id:
            raise ValueError("Tenant UUID must be lowercase and canonical")
        if not isinstance(self.slug, str) or not _SLUG.fullmatch(self.slug):
            raise ValueError("Invalid tenant slug")
        if not isinstance(self.whatsapp_phone_id, str) or not _PROVIDER.fullmatch(self.whatsapp_phone_id):
            raise ValueError("Invalid trusted WhatsApp account ID")
        if (
            not isinstance(self.database_role, str)
            or not _ROLE.fullmatch(self.database_role)
            or self.database_role in _FORBIDDEN_ROLES
        ):
            raise ValueError("Unsafe database login role")
        if not isinstance(self.database_password, str) or len(self.database_password) < 32:
            raise ValueError("Tenant DB role secret must contain at least 32 characters")
        if not isinstance(self.database_host, str) or not self.database_host or len(self.database_host) > 253:
            raise ValueError("Invalid provisioned database host")
        if not isinstance(self.database_name, str) or not self.database_name or len(self.database_name) > 63:
            raise ValueError("Invalid provisioned database name")
        if type(self.database_port) is not int or not 1 <= self.database_port <= 65535:
            raise ValueError("Invalid database port")


@dataclass
class _Slot:
    tenant_id: str
    slug: str
    whatsapp_phone_id: str
    database_role: str
    engine: Engine
    factory: sessionmaker
    active_leases: int = 0
    retired: bool = False


class TenantPoolLease:
    """A request must keep this lease open until its transaction finishes."""

    def __init__(self, registry: "StagedTenantPoolRegistry", slot: _Slot):
        self._registry = registry
        self._slot = slot
        self._released = False

    @property
    def factory(self):
        if self._released:
            raise RuntimeError("Tenant DB lease has been released")
        return self._slot.factory

    @property
    def tenant_id(self):
        return self._slot.tenant_id

    def __enter__(self):
        if self._released:
            raise RuntimeError("Tenant DB lease cannot be re-entered")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        if not self._released:
            self._released = True
            self._registry._release(self._slot)


class StagedTenantPoolRegistry:
    """Bounded per-process tenant engine registry with fail-closed lifecycle.

    The injected factory is only for deterministic unit testing. A real
    registration always verifies the authenticated PostgreSQL login and the
    SECURITY DEFINER tenant mapping before an engine can become visible.
    """

    def __init__(
        self,
        *,
        max_tenants: int = 8,
        pool_size: int = 2,
        engine_builder: Callable[..., Engine] = create_engine,
    ):
        if type(max_tenants) is not int or not 1 <= max_tenants <= 16:
            raise ValueError("max_tenants must be 1..16")
        if type(pool_size) is not int or not 1 <= pool_size <= 4:
            raise ValueError("pool_size must be 1..4")
        if max_tenants * pool_size > 32:
            raise ValueError("Total allowed persistent DB connections exceeds safe staged budget")
        if not callable(engine_builder):
            raise ValueError("Engine builder must be callable")
        self._max_tenants = max_tenants
        self._pool_size = pool_size
        self._engine_builder = engine_builder
        self._by_tenant: dict[str, _Slot] = {}
        self._by_slug: dict[str, str] = {}
        self._by_phone: dict[str, str] = {}
        self._retiring_roles: set[str] = set()
        self._closed = False
        self._lock = threading.RLock()

    def _validate_login(self, engine: Engine, config: TenantPrincipalConfig):
        # Access to PostgreSQL catalog role attributes is read-only.
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT current_user::text, session_user::text, "
                    "medtour_principal_private.tenant_for_login()::text, "
                    "r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb, "
                    "r.rolreplication, has_table_privilege('public.tenants', 'SELECT') "
                    "FROM pg_roles r WHERE r.rolname=session_user"
                )
            ).one()
            login, session_user, mapped, is_super, bypass, create_role, create_db, replicate, read_global = row
            if (
                login != config.database_role
                or session_user != config.database_role
                or mapped != config.tenant_id
                or any((is_super, bypass, create_role, create_db, replicate, read_global))
            ):
                raise PermissionError("Database login fails tenant isolation or least-privilege proof")

    def enroll(self, config: TenantPrincipalConfig) -> None:
        """Provision ONLY trusted configs; duplicate and capacity checks are atomic."""
        if not isinstance(config, TenantPrincipalConfig):
            raise ValueError("Expected an explicitly provisioned tenant config")
        # Preflight duplicate/capacity checks avoid creating unnecessary engines.
        with self._lock:
            if self._closed:
                raise RuntimeError("Tenant registry is shut down")
            self._assert_available(config)

        url = URL.create(
            "postgresql+psycopg",
            username=config.database_role,
            password=config.database_password,
            host=config.database_host,
            port=config.database_port,
            database=config.database_name,
        )
        engine = self._engine_builder(
            url,
            pool_size=self._pool_size,
            max_overflow=0,
            pool_timeout=5,
            pool_pre_ping=True,
            pool_reset_on_return="rollback",
            connect_args={"connect_timeout": 5},
        )
        accepted = False
        try:
            self._validate_login(engine, config)
            factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
            with self._lock:
                if self._closed:
                    raise RuntimeError("Tenant registry is shut down")
                self._assert_available(config)
                self._by_tenant[config.tenant_id] = _Slot(
                    config.tenant_id, config.slug, config.whatsapp_phone_id,
                    config.database_role, engine, factory,
                )
                self._by_slug[config.slug] = config.tenant_id
                self._by_phone[config.whatsapp_phone_id] = config.tenant_id
                accepted = True
        finally:
            if not accepted:
                engine.dispose()

    def _assert_available(self, config: TenantPrincipalConfig):
        if len(self._by_tenant) >= self._max_tenants:
            raise ValueError("Bounded tenant pool capacity exceeded")
        if (
            config.tenant_id in self._by_tenant
            or config.slug in self._by_slug
            or config.whatsapp_phone_id in self._by_phone
        ):
            raise ValueError("Duplicate tenant, slug or WhatsApp provider mapping")
        if config.database_role in self._retiring_roles or any(
            s.database_role == config.database_role for s in self._by_tenant.values()
        ):
            raise ValueError("A PostgreSQL LOGIN role cannot be shared by tenants")

    def _acquire(self, tenant_id: str) -> TenantPoolLease:
        with self._lock:
            if self._closed:
                raise LookupError("Tenant registry is unavailable")
            slot = self._by_tenant.get(tenant_id)
            if slot is None or slot.retired:
                raise LookupError("Tenant is not provisioned")
            slot.active_leases += 1
            return TenantPoolLease(self, slot)

    def acquire_tenant(self, tenant_id: str):
        return self._acquire(tenant_id)

    def acquire_slug(self, slug: str):
        with self._lock:
            tid = self._by_slug.get(slug)
            if tid is None:
                raise LookupError("Tenant slug not provisioned")
            return self._acquire(tid)

    def acquire_phone(self, phone_id: str):
        with self._lock:
            tid = self._by_phone.get(phone_id)
            if tid is None:
                raise LookupError("WhatsApp account not provisioned")
            return self._acquire(tid)

    def _release(self, slot: _Slot):
        dispose = False
        with self._lock:
            if slot.active_leases <= 0:
                raise RuntimeError("Invalid tenant lease release")
            slot.active_leases -= 1
            dispose = slot.retired and slot.active_leases == 0
            if dispose:
                self._retiring_roles.discard(slot.database_role)
        if dispose:
            slot.engine.dispose()

    def revoke(self, tenant_id: str):
        """Stop new routing immediately; allow already-started leases to drain."""
        engine_to_dispose = None
        with self._lock:
            slot = self._by_tenant.pop(tenant_id, None)
            if slot is None:
                raise LookupError("Tenant not provisioned")
            slot.retired = True
            self._by_slug.pop(slot.slug, None)
            self._by_phone.pop(slot.whatsapp_phone_id, None)
            if slot.active_leases == 0:
                engine_to_dispose = slot.engine
            else:
                self._retiring_roles.add(slot.database_role)
        if engine_to_dispose is not None:
            engine_to_dispose.dispose()

    def close(self):
        to_dispose = []
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for slot in self._by_tenant.values():
                slot.retired = True
                if slot.active_leases == 0:
                    to_dispose.append(slot.engine)
                else:
                    self._retiring_roles.add(slot.database_role)
            self._by_tenant.clear()
            self._by_slug.clear()
            self._by_phone.clear()
        for engine in to_dispose:
            engine.dispose()

    def snapshot_counts(self) -> dict[str, int | bool]:
        """Return only aggregate counters; never role names or credentials."""
        with self._lock:
            return {
                "tenants": len(self._by_tenant),
                "active_leases": sum(s.active_leases for s in self._by_tenant.values()),
                "max_tenants": self._max_tenants,
                "connections_budget": self._max_tenants * self._pool_size,
                "closed": self._closed,
            }
