"""Active health probe: database, Alembic head and configured Redis.

Never disclose DB URLs, secrets, credentials or patient data in responses.
SQLite is accepted for isolated synthetic tests only. This probe does not
certify tenant RLS, clinical safety or production readiness.
"""
from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import Tenant


def required_revision() -> str:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if not head:
        raise RuntimeError("No Alembic migration head exists")
    return head


def check_migrations(db: Session) -> str:
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        if os.getenv("APP_ENV", "development") not in ("test", "development"):
            raise RuntimeError("SQLite is limited to development and synthetic tests")
        return "not_checked_sqlite"
    if dialect != "postgresql":
        raise RuntimeError("Unsupported database dialect")
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if current != required_revision():
        raise RuntimeError("Database migration is not at the current Alembic head")
    return "current"


def check_redis(redis_url: str) -> bool:
    from redis import Redis
    if not redis_url.startswith(("redis://", "rediss://")):
        raise RuntimeError("Unsupported Redis URL scheme")
    connection = Redis.from_url(
        redis_url, socket_timeout=2, socket_connect_timeout=2, retry_on_timeout=False
    )
    try:
        return bool(connection.ping())
    finally:
        connection.close()


def probe_stack(db: Session) -> dict:
    db.execute(select(func.count()).select_from(Tenant)).scalar_one()
    migration = check_migrations(db)
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url and not check_redis(redis_url):
        raise RuntimeError("Configured Redis dependency is not ready")
    return {
        "status": "ready",
        "database": "reachable",
        "schema_migration": migration,
        "redis": "reachable" if redis_url else "not_configured",
        "production_ready": False,
    }
