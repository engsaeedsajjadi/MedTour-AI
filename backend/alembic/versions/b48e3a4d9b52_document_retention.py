"""Medical documents: envelope-encryption key, legal hold and cryptographic erasure timestamp."""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "b48e3a4d9b52"
down_revision = "b47d2f3c8a41"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("wrapped_key", sa.String(length=200), nullable=True))
    op.add_column("documents", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("documents", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("documents", "erased_at")
    op.drop_column("documents", "legal_hold")
    op.drop_column("documents", "wrapped_key")
