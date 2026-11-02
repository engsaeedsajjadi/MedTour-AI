"""Per-transaction tenant context for PostgreSQL row-level security.

Every tenant-owned table carries a policy that only returns rows whose
``tenant_id`` equals ``current_setting('app.tenant_id')``. The API binds that
value from the *verified* identity (staff JWT, patient portal grant, consent
link, ...) before touching tenant data. Nothing is bound by default, so a
handler that forgets its own ``tenant_id`` filter gets an empty result instead
of another customer's rows.

Values are applied with ``set_config(..., is_local => true)`` at the start of
every transaction, so they never leak to the next request through the
connection pool.

``system_scope`` exists only for code that must resolve a tenant before it is
known (login by slug is not needed — ``tenants`` has no RLS — but token-hash
lookups are) and for background workers. Each use is explicit and short.
"""
from __future__ import annotations
import os
from contextlib import contextmanager
from sqlalchemy import event, text
from sqlalchemy.orm import Session

TENANT_KEY = "medtour_tenant_id"
SCOPE_KEY = "medtour_tenant_scope"
_APPLY = text("SELECT set_config('app.tenant_id', :tenant, true), set_config('app.tenant_scope', :scope, true)")


def _is_postgres(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def _default_scope() -> str:
    # Background worker processes (outbound delivery, bootstrap) set MEDTOUR_WORKER_SCOPE=system.
    # The API process never sets it, so API sessions start with no tenant and see nothing.
    return "system" if os.getenv("MEDTOUR_WORKER_SCOPE", "") == "system" else ""


def _apply(session: Session, connection=None) -> None:
    params = {"tenant": session.info.get(TENANT_KEY) or "",
              "scope": session.info.get(SCOPE_KEY) or ("" if session.info.get(TENANT_KEY) else _default_scope())}
    if connection is not None:
        connection.execute(_APPLY, params)
    elif session.in_transaction():
        session.connection().execute(_APPLY, params)


@event.listens_for(Session, "after_begin")
def _set_context_on_begin(session, transaction, connection):  # pragma: no cover - exercised on PostgreSQL
    if connection.dialect.name == "postgresql":
        _apply(session, connection)


def bind_tenant(session: Session, tenant_id: str | None) -> None:
    """Restrict this session to one tenant for the rest of the request."""
    session.info[TENANT_KEY] = str(tenant_id) if tenant_id else ""
    session.info[SCOPE_KEY] = "tenant" if tenant_id else ""
    if _is_postgres(session):
        _apply(session)


def bound_tenant(session: Session) -> str:
    return session.info.get(TENANT_KEY) or ""


@contextmanager
def system_scope(session: Session):
    """Temporarily read across tenants. Use only to resolve a tenant from a secret or in workers."""
    previous = session.info.get(SCOPE_KEY) or ""
    session.info[SCOPE_KEY] = "system"
    try:
        if _is_postgres(session):
            _apply(session)
        yield session
    finally:
        session.info[SCOPE_KEY] = previous
        if _is_postgres(session) and session.in_transaction():
            _apply(session)


def worker_session(factory):
    """A session for background workers that legitimately process all tenants."""
    session = factory()
    session.info[SCOPE_KEY] = "system"
    return session
