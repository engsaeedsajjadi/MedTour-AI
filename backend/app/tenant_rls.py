"""Row-level security installation and runtime verification (PostgreSQL only).

``install_rls`` is idempotent and is used by the Alembic migration and by the
PostgreSQL test harness, so production and tests run the very same policies.
"""
from __future__ import annotations
import os
import re
from sqlalchemy import text

APP_ROLE = os.getenv("APP_DB_ROLE", "medtour_app")
POLICY = "mt_tenant_isolation"
LEGACY_POLICY = "mt26_principal_isolation"
_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

TENANT_TABLES_SQL = """
 SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id'
 WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
 ORDER BY c.relname
"""
CONDITION = ("(tenant_id::text = current_setting('app.tenant_id', true) "
             "OR current_setting('app.tenant_scope', true) = 'system')")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _role(name: str) -> str:
    if not _ROLE_RE.fullmatch(name):
        raise ValueError("Unsafe database role name")
    return name


def tenant_tables(conn) -> list[str]:
    return list(conn.execute(text(TENANT_TABLES_SQL)).scalars())


def install_rls(conn, app_role: str = APP_ROLE) -> int:
    """Create the non-privileged runtime role, grant it data access only, and enforce RLS."""
    role = _role(app_role)
    conn.execute(text(f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
        END $$"""))
    conn.execute(text(f"ALTER ROLE {role} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"))
    conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"))
    conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}"))
    conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"))
    conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}"))
    # The migration bookkeeping table is not application data.
    conn.execute(text(f"""
        DO $$ BEGIN
          IF to_regclass('public.alembic_version') IS NOT NULL THEN
            REVOKE INSERT, UPDATE, DELETE ON public.alembic_version FROM {role};
          END IF;
        END $$"""))
    tables = tenant_tables(conn)
    for table in tables:
        t = _q(table)
        conn.execute(text(f"DROP POLICY IF EXISTS {LEGACY_POLICY} ON public.{t}"))
        conn.execute(text(f"DROP POLICY IF EXISTS {POLICY} ON public.{t}"))
        conn.execute(text(f"CREATE POLICY {POLICY} ON public.{t} FOR ALL USING {CONDITION} WITH CHECK {CONDITION}"))
        conn.execute(text(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"ALTER TABLE public.{t} FORCE ROW LEVEL SECURITY"))
    return len(tables)


def set_app_role_login(conn, password: str, app_role: str = APP_ROLE) -> None:
    """Allow the runtime role to log in (password comes from the environment, never from code)."""
    role = _role(app_role)
    if len(password) < 16:
        raise ValueError("APP_DB_PASSWORD must contain at least 16 characters")
    escaped = password.replace("'", "''")
    conn.execute(text(f"ALTER ROLE {role} LOGIN PASSWORD '{escaped}'"))


def runtime_status(conn) -> dict:
    """What the running API connection actually gets from PostgreSQL."""
    role = conn.execute(text("""
        SELECT r.rolsuper, r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user
    """)).one()
    scoped = conn.execute(text(f"SELECT count(*) FROM ({TENANT_TABLES_SQL}) t")).scalar()
    enforced = conn.execute(text("""
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id'
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
          AND c.relrowsecurity AND c.relforcerowsecurity
          AND EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname='public'
                      AND p.tablename=c.relname AND p.policyname=:policy)
    """), {"policy": POLICY}).scalar()
    nonprivileged = not role[0] and not role[1]
    return {
        "tenant_scoped_tables": int(scoped),
        "rls_enforced_tables": int(enforced),
        "runtime_role_nonprivileged": bool(nonprivileged),
        "rls_effective": bool(nonprivileged and scoped > 0 and enforced == scoped),
    }


def assert_runtime_isolation(engine) -> dict | None:
    """Refuse to serve requests when isolation is required but not effective."""
    if engine.dialect.name != "postgresql":
        return None
    with engine.connect() as conn:
        status = runtime_status(conn)
    required = (os.getenv("RLS_ENFORCEMENT", "").lower() == "required"
                or os.getenv("APP_ENV", "development") == "production")
    if required and not status["rls_effective"]:
        raise RuntimeError(
            "Tenant isolation is not effective: the API must connect as the non-privileged "
            f"'{APP_ROLE}' role and every tenant table must have forced RLS. Run migrations and "
            "set DATABASE_URL to the application role.")
    return status
