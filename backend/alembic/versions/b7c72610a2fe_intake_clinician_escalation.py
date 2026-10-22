"""Add nonclinical intake review and locally attested reviewer credentials.

Revision ID: b7c72610a2fe
Revises: 71dcbcd5f22b
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c72610a2fe"
down_revision = "71dcbcd5f22b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reviewer_credentials",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issuing_country", sa.String(2), nullable=False),
        sa.Column("issuing_authority", sa.String(120), nullable=False),
        sa.Column("verification_reference", sa.String(100), nullable=False),
        sa.Column("checked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id"),
    )
    op.create_index("ix_reviewer_credentials_tenant_id", "reviewer_credentials", ["tenant_id"])
    op.create_index("ix_reviewer_credentials_user_id", "reviewer_credentials", ["user_id"])
    op.create_table(
        "intake_review_records",
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("intake_id", sa.String(36), sa.ForeignKey("patient_intakes.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(55), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("external_confirmation", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "intake_id", "action", "reference"),
    )
    op.create_index("ix_intake_review_records_tenant_id", "intake_review_records", ["tenant_id"])
    op.create_index("ix_intake_review_records_case_id", "intake_review_records", ["case_id"])
    op.create_index("ix_intake_review_records_intake_id", "intake_review_records", ["intake_id"])


    op.create_table(
        "intake_reviewer_assignments",
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("intake_id", sa.String(36), sa.ForeignKey("patient_intakes.id"), nullable=False),
        sa.Column("reviewer_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "intake_id", "reviewer_user_id"),
    )
    op.create_index("ix_intake_reviewer_assignments_tenant_id", "intake_reviewer_assignments", ["tenant_id"])
    op.create_index("ix_intake_reviewer_assignments_case_id", "intake_reviewer_assignments", ["case_id"])
    op.create_index("ix_intake_reviewer_assignments_intake_id", "intake_reviewer_assignments", ["intake_id"])
    op.create_index("ix_intake_reviewer_assignments_reviewer_user_id", "intake_reviewer_assignments", ["reviewer_user_id"])


def downgrade():
    op.drop_index("ix_intake_reviewer_assignments_reviewer_user_id", table_name="intake_reviewer_assignments")
    op.drop_index("ix_intake_reviewer_assignments_intake_id", table_name="intake_reviewer_assignments")
    op.drop_index("ix_intake_reviewer_assignments_case_id", table_name="intake_reviewer_assignments")
    op.drop_index("ix_intake_reviewer_assignments_tenant_id", table_name="intake_reviewer_assignments")
    op.drop_table("intake_reviewer_assignments")
    op.drop_index("ix_intake_review_records_intake_id", table_name="intake_review_records")
    op.drop_index("ix_intake_review_records_case_id", table_name="intake_review_records")
    op.drop_index("ix_intake_review_records_tenant_id", table_name="intake_review_records")
    op.drop_table("intake_review_records")
    op.drop_index("ix_reviewer_credentials_user_id", table_name="reviewer_credentials")
    op.drop_index("ix_reviewer_credentials_tenant_id", table_name="reviewer_credentials")
    op.drop_table("reviewer_credentials")
