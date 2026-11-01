"""Enforce tenant row-level security with a non-privileged runtime role.

Creates the ``medtour_app`` role (no superuser, no BYPASSRLS, data access
only), replaces the never-activated Section 26 principal policies with
per-transaction tenant policies, and ENABLE + FORCE row-level security on every
table that has a ``tenant_id`` column.

The API must connect as ``medtour_app``; migrations keep using the owner role.
The role's login password is set separately by ``app.provision_db`` from the
APP_DB_PASSWORD environment variable.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "b46c1e2a7f30"
down_revision = "a37e904d12ab"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    from app.tenant_rls import install_rls
    installed = install_rls(conn)
    if installed < 37:
        raise RuntimeError("Tenant schema drift: expected at least 37 tenant-owned tables")


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    from app.tenant_rls import POLICY, tenant_tables, _q
    for table in tenant_tables(conn):
        t = _q(table)
        conn.execute(sa.text(f"ALTER TABLE public.{t} NO FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE public.{t} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {POLICY} ON public.{t}"))
