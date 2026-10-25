"""Section 17: isolated, consent-controlled administrative medical-visa records.
Revision ID: a17e526a13c9
Revises: a16b7d20f4ce
"""
from alembic import op
import sqlalchemy as sa

revision = "a17e526a13c9"
down_revision = "a16b7d20f4ce"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("medical_visas",
      sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
      sa.Column("id", sa.String(36), primary_key=True, nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
      sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False),
      sa.Column("origin_country", sa.String(2), nullable=False),
      sa.Column("destination_country", sa.String(2), nullable=False),
      sa.Column("visa_type", sa.String(24), nullable=False),
      sa.Column("request_key", sa.String(100), nullable=False),
      sa.Column("intended_departure_at", sa.DateTime(timezone=True), nullable=True),
      sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True),
      sa.Column("status", sa.String(36), nullable=False),
      sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
      sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
      sa.Column("authority_name", sa.String(100), nullable=True),
      sa.Column("external_reference", sa.String(100), nullable=True),
      sa.Column("decision_reported", sa.String(40), nullable=True),
      sa.UniqueConstraint("tenant_id", "case_id", "request_key"))
    op.create_index("ix_medical_visas_tenant_id", "medical_visas", ["tenant_id"])
    op.create_index("idx_medical_visas_due", "medical_visas", ["tenant_id", "status", "next_action_due_at"])
    op.create_table("medical_visa_checklist",
      sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
      sa.Column("id", sa.String(36), primary_key=True, nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.Column("application_id", sa.String(36), sa.ForeignKey("medical_visas.id"), nullable=False),
      sa.Column("item_key", sa.String(40), nullable=False),
      sa.Column("status", sa.String(30), nullable=False),
      sa.Column("review_reference", sa.String(100), nullable=True),
      sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
      sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
      sa.UniqueConstraint("tenant_id", "application_id", "item_key"))
    op.create_index("ix_medical_visa_checklist_tenant_id", "medical_visa_checklist", ["tenant_id"])
    op.create_table("medical_visa_events",
      sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
      sa.Column("id", sa.String(36), primary_key=True, nullable=False),
      sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
      sa.Column("application_id", sa.String(36), sa.ForeignKey("medical_visas.id"), nullable=False),
      sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
      sa.Column("step_key", sa.String(100), nullable=False),
      sa.Column("fingerprint", sa.String(64), nullable=False),
      sa.Column("action", sa.String(40), nullable=False),
      sa.Column("old_status", sa.String(36), nullable=False),
      sa.Column("new_status", sa.String(36), nullable=False),
      sa.Column("reference", sa.String(100), nullable=False),
      sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
      sa.UniqueConstraint("tenant_id", "application_id", "step_key"))
    op.create_index("ix_medical_visa_events_tenant_id", "medical_visa_events", ["tenant_id"])

def downgrade():
    op.drop_index("ix_medical_visa_events_tenant_id", table_name="medical_visa_events")
    op.drop_table("medical_visa_events")
    op.drop_index("ix_medical_visa_checklist_tenant_id", table_name="medical_visa_checklist")
    op.drop_table("medical_visa_checklist")
    op.drop_index("idx_medical_visas_due", table_name="medical_visas")
    op.drop_index("ix_medical_visas_tenant_id", table_name="medical_visas")
    op.drop_table("medical_visas")
