"""Prevent duplicate confirmed slots for the same tenant, physician and instant.

Revision ID: 9a4e1ce5039b
Revises: 831ed6424f1c

An existing database with contradictory confirmed slots must be reconciled
by the clinical scheduling operator BEFORE applying this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = '9a4e1ce5039b'
down_revision = '831ed6424f1c'
branch_labels = None
depends_on = None

INDEX = 'uq_appointments_confirmed_physician_instant'


def upgrade() -> None:
    op.create_index(
        INDEX,
        'appointments',
        ['tenant_id', 'physician_id', 'requested_at'],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
        sqlite_where=sa.text("status = 'confirmed'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name='appointments')
