"""Run after ``alembic upgrade head`` with the database OWNER connection.

* re-applies row-level security to every tenant table (covers tables added by later migrations)
* lets the non-privileged runtime role log in with APP_DB_PASSWORD

Usage (docker compose ``migrate`` service): ``python -m alembic upgrade head && python -m app.provision_db``
"""
from __future__ import annotations
import os
import sys
from sqlalchemy import create_engine, text
from .tenant_rls import APP_ROLE, install_rls, set_app_role_login


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        print("provision_db: PostgreSQL owner DSN required; nothing to do")
        return 0
    password = os.environ.get("APP_DB_PASSWORD", "")
    engine = create_engine(url)
    with engine.begin() as conn:
        if conn.execute(text("SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname=current_user")).scalar() is not True:
            print("provision_db: must run as the database owner/superuser, not the application role", file=sys.stderr)
            return 2
        count = install_rls(conn)
        if password:
            set_app_role_login(conn, password)
        elif os.getenv("APP_ENV", "development") == "production":
            print("provision_db: APP_DB_PASSWORD is required in production", file=sys.stderr)
            return 2
    print(f"provision_db: row-level security enforced on {count} tables; runtime role '{APP_ROLE}'"
          + (" can log in" if password else " has no login (APP_DB_PASSWORD not set)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
