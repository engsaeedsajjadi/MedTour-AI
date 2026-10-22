"""Section 09 Patient CRM migration. Revision ID c9d093e78a21."""
from alembic import op
import sqlalchemy as sa

revision="c9d093e78a21"
down_revision="b8d08c4ea132"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "crm_followups",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),
        sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("assigned_user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("idempotency_key",sa.String(100),nullable=False),
        sa.Column("due_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("reason_code",sa.String(40),nullable=False),
        sa.Column("status",sa.String(35),nullable=False),
        sa.Column("outcome_code",sa.String(40),nullable=True),
        sa.Column("completion_reference",sa.String(100),nullable=True),
        sa.Column("resolved_at",sa.DateTime(timezone=True),nullable=True),
        sa.UniqueConstraint("tenant_id","case_id","idempotency_key"),
    )
    for col in ("tenant_id","case_id","patient_id"):
        op.create_index("ix_crm_followups_"+col,"crm_followups",[col])
    op.create_index("idx_crm_followups_queue","crm_followups",["tenant_id","status","due_at"])
    op.create_table(
        "crm_duplicate_reviews",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("left_patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("right_patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("decision",sa.String(32),nullable=False),
        sa.Column("reviewer_user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("evidence_reference",sa.String(100),nullable=False),
        sa.UniqueConstraint("tenant_id","left_patient_id","right_patient_id"),
    )
    op.create_index("ix_crm_duplicate_reviews_tenant_id","crm_duplicate_reviews",["tenant_id"])

def downgrade():
    op.drop_index("ix_crm_duplicate_reviews_tenant_id",table_name="crm_duplicate_reviews")
    op.drop_table("crm_duplicate_reviews")
    op.drop_index("idx_crm_followups_queue",table_name="crm_followups")
    for col in ("patient_id","case_id","tenant_id"):
        op.drop_index("ix_crm_followups_"+col,table_name="crm_followups")
    op.drop_table("crm_followups")
