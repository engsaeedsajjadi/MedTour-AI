"""Run versioned migrations on a disposable synthetic SQLite database.

PostgreSQL + tenant RLS still require a separate isolated-clone acceptance test.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_alembic_head_includes_tenant_subscription_and_reversible_delta(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / 'synthetic_migrations.sqlite3'
    env = dict(os.environ)
    env['DATABASE_URL'] = 'sqlite:///' + str(database)
    env['APP_ENV'] = 'test'

    def alembic(*args):
        result = subprocess.run(
            [sys.executable, '-m', 'alembic', *args],
            cwd=backend, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=75, check=False,
        )
        assert result.returncode == 0, result.stdout

    alembic('upgrade', 'head')
    with sqlite3.connect(database) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert 'tenant_subscriptions' in tables
        cols = {
            row[1] for row in connection.execute(
                'PRAGMA table_info(tenant_subscriptions)'
            )
        }
        assert {'tenant_id', 'plan_code', 'status', 'activated_by',
                'created_at', 'expires_at'}.issubset(cols)
        appointment_cols = {
            row[1] for row in connection.execute('PRAGMA table_info(appointments)')
        }
        assert {'cancellation_reference', 'cancelled_at'} <= appointment_cols
        indexes = {row[1] for row in connection.execute('PRAGMA index_list(appointments)')}
        assert 'uq_appointments_confirmed_physician_instant' in indexes

    alembic('downgrade', '71dcbcd5f22b')
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name='tenant_subscriptions'"
        ).fetchone()[0] == 0

    alembic('upgrade', 'head')
