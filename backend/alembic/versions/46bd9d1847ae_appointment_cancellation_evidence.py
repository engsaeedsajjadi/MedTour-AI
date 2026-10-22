"""Record independent provider cancellation reference without erasing confirmation.

Revision ID: 46bd9d1847ae
Revises: 9a4e1ce5039b
"""
from alembic import op
import sqlalchemy as sa

revision = '46bd9d1847ae'
down_revision = '9a4e1ce5039b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('appointments', sa.Column(
        'cancellation_reference', sa.String(length=120), nullable=True
    ))
    op.add_column('appointments', sa.Column(
        'cancelled_at', sa.DateTime(timezone=True), nullable=True
    ))


def downgrade() -> None:
    op.drop_column('appointments', 'cancelled_at')
    op.drop_column('appointments', 'cancellation_reference')
