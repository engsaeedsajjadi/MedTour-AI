"""Physician identity, credential evidence, hospital affiliation and slots.

Revision ID: e12c97f30a2d
Revises: d11ab47302c1
"""
from alembic import op
import sqlalchemy as sa

revision = "e12c97f30a2d"
down_revision = "d11ab47302c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "physician_accounts",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("physician_id", sa.String(36), sa.ForeignKey("physicians.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("linked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tenant_id", "physician_id"),
        sa.UniqueConstraint("tenant_id", "user_id"),
    )
    op.create_index("ix_physician_accounts_tenant_id", "physician_accounts", ["tenant_id"])
    op.create_index("ix_physician_accounts_physician_id", "physician_accounts", ["physician_id"])
    op.create_index("ix_physician_accounts_user_id", "physician_accounts", ["user_id"])
    op.create_table(
        "physician_credentials",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("physician_id", sa.String(36), sa.ForeignKey("physicians.id"), nullable=False),
        sa.Column("issuing_country", sa.String(2), nullable=False),
        sa.Column("issuing_authority", sa.String(120), nullable=False),
        sa.Column("license_reference", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "physician_id"),
    )
    op.create_index("ix_physician_credentials_tenant_id", "physician_credentials", ["tenant_id"])
    op.create_index("ix_physician_credentials_physician_id", "physician_credentials", ["physician_id"])
    op.create_table(
        "physician_affiliations",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("physician_id", sa.String(36), sa.ForeignKey("physicians.id"), nullable=False),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("tenant_id", "physician_id", "hospital_id"),
    )
    op.create_index("ix_physician_affiliations_tenant_id", "physician_affiliations", ["tenant_id"])
    op.create_index("ix_physician_affiliations_physician_id", "physician_affiliations", ["physician_id"])
    op.create_index("ix_physician_affiliations_hospital_id", "physician_affiliations", ["hospital_id"])
    op.create_table(
        "physician_availability",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("physician_id", sa.String(36), sa.ForeignKey("physicians.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_physician_availability_tenant_id", "physician_availability", ["tenant_id"])
    op.create_index("ix_physician_availability_physician_id", "physician_availability", ["physician_id"])
    op.create_index("idx_physician_availability_tenant_window", "physician_availability", ["tenant_id", "physician_id", "starts_at"])


def downgrade():
    for index in ("idx_physician_availability_tenant_window", "ix_physician_availability_physician_id", "ix_physician_availability_tenant_id"):
        op.drop_index(index, table_name="physician_availability")
    op.drop_table("physician_availability")
    for index in ("ix_physician_affiliations_hospital_id", "ix_physician_affiliations_physician_id", "ix_physician_affiliations_tenant_id"):
        op.drop_index(index, table_name="physician_affiliations")
    op.drop_table("physician_affiliations")
    for index in ("ix_physician_credentials_physician_id", "ix_physician_credentials_tenant_id"):
        op.drop_index(index, table_name="physician_credentials")
    op.drop_table("physician_credentials")
    for index in ("ix_physician_accounts_user_id", "ix_physician_accounts_physician_id", "ix_physician_accounts_tenant_id"):
        op.drop_index(index, table_name="physician_accounts")
    op.drop_table("physician_accounts")
