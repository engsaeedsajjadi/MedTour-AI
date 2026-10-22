"""Tenant subscription provisioning (technical entitlements only).

Revision ID: 831ed6424f1c
Revises: 71dcbcd5f22b
"""
from alembic import op
import sqlalchemy as sa

revision = '831ed6424f1c'
down_revision = '71dcbcd5f22b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenant_subscriptions',
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('plan_code', sa.String(length=24), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('activated_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['activated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('tenant_id'),
    )


def downgrade() -> None:
    op.drop_table('tenant_subscriptions')
