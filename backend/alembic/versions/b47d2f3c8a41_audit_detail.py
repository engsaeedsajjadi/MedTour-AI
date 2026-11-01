"""Audit trail: optional non-sensitive detail (route, reason) for security events."""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "b47d2f3c8a41"
down_revision = "b46c1e2a7f30"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_events", sa.Column("detail", sa.String(length=300), nullable=True))


def downgrade():
    op.drop_column("audit_events", "detail")
