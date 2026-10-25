"""Section 14 provider match proposals.
Revision ID: a14a62c391dd
Revises: f13bc720a5e1
"""
from alembic import op
import sqlalchemy as sa
revision="a14a62c391dd"
down_revision="f13bc720a5e1"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("provider_matches",
      sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
      sa.Column("id",sa.String(36),primary_key=True,nullable=False),
      sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
      sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),
      sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
      sa.Column("physician_id",sa.String(36),sa.ForeignKey("physicians.id"),nullable=False),
      sa.Column("hospital_id",sa.String(36),sa.ForeignKey("hospitals.id"),nullable=True),
      sa.Column("status",sa.String(30),nullable=False),
      sa.Column("proposed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
      sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
      sa.Column("review_reference",sa.String(100),nullable=True),
      sa.Column("reviewed_at",sa.DateTime(timezone=True),nullable=True),
      sa.UniqueConstraint("tenant_id","case_id","physician_id","hospital_id"),
    )
    for col in ("tenant_id","case_id"):
        op.create_index("ix_provider_matches_"+col,"provider_matches",[col])

def downgrade():
    for col in ("case_id","tenant_id"):
        op.drop_index("ix_provider_matches_"+col,table_name="provider_matches")
    op.drop_table("provider_matches")
