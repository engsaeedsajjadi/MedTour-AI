"""Section 16 manual, auditable minor-unit FX rate references.
Revision ID: a16b7d20f4ce
Revises: a16ef029c5d1
"""
from alembic import op
import sqlalchemy as sa
revision="a16b7d20f4ce"
down_revision="a16ef029c5d1"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("verified_fx_rates",
      sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
      sa.Column("id",sa.String(36),primary_key=True,nullable=False),
      sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
      sa.Column("source_currency",sa.String(3),nullable=False),
      sa.Column("target_currency",sa.String(3),nullable=False),
      sa.Column("numerator",sa.BigInteger(),nullable=False),
      sa.Column("denominator",sa.BigInteger(),nullable=False),
      sa.Column("source_reference",sa.String(180),nullable=False),
      sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
      sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
      sa.Column("active",sa.Boolean(),nullable=False))
    op.create_index("ix_verified_fx_rates_tenant_id","verified_fx_rates",["tenant_id"])
    op.create_index("idx_fx_rates_tenant_pair","verified_fx_rates",["tenant_id","source_currency","target_currency"])

def downgrade():
    op.drop_index("idx_fx_rates_tenant_pair",table_name="verified_fx_rates")
    op.drop_index("ix_verified_fx_rates_tenant_id",table_name="verified_fx_rates")
    op.drop_table("verified_fx_rates")
