"""Section 08 medical-document access trail for patient/staff attribution.

Revision ID: b8d08c4ea132
Revises: b7c72610a2fe
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d08c4ea132"
down_revision = "b7c72610a2fe"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "medical_document_events",
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("staff_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("portal_access_id", sa.String(36), sa.ForeignKey("portal_access.id"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_medical_document_events_tenant_id", "medical_document_events", ["tenant_id"])
    op.create_index("ix_medical_document_events_document_id", "medical_document_events", ["document_id"])
    op.create_index("ix_medical_document_events_case_id", "medical_document_events", ["case_id"])
    op.create_index("idx_medical_document_events_tenant_case", "medical_document_events", ["tenant_id", "case_id"])


def downgrade():
    op.drop_index("idx_medical_document_events_tenant_case", table_name="medical_document_events")
    op.drop_index("ix_medical_document_events_case_id", table_name="medical_document_events")
    op.drop_index("ix_medical_document_events_document_id", table_name="medical_document_events")
    op.drop_index("ix_medical_document_events_tenant_id", table_name="medical_document_events")
    op.drop_table("medical_document_events")
