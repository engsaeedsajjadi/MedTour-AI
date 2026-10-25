"""Section 15 calendar allocations, revision a15c18e2674b."""
from alembic import op
import sqlalchemy as sa
revision="a15c18e2674b"
down_revision="a14a62c391dd"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("appointment_slots",
      sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
      sa.Column("id",sa.String(36),primary_key=True,nullable=False),
      sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
      sa.Column("appointment_id",sa.String(36),sa.ForeignKey("appointments.id"),nullable=False,unique=True),
      sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),
      sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
      sa.Column("physician_id",sa.String(36),sa.ForeignKey("physicians.id"),nullable=False),
      sa.Column("availability_id",sa.String(36),sa.ForeignKey("physician_availability.id"),nullable=True),
      sa.Column("ends_at",sa.DateTime(timezone=True),nullable=False),
      sa.Column("status",sa.String(24),nullable=False),
      sa.Column("request_key",sa.String(100),nullable=False),
      sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
      sa.Column("review_reference",sa.String(100),nullable=True),
      sa.UniqueConstraint("tenant_id","case_id","request_key"))
    op.create_index("ix_appointment_slots_tenant_id","appointment_slots",["tenant_id"])
    op.create_index("idx_appointment_slots_resource","appointment_slots",["tenant_id","physician_id","status"])

def downgrade():
    op.drop_index("idx_appointment_slots_resource",table_name="appointment_slots")
    op.drop_index("ix_appointment_slots_tenant_id",table_name="appointment_slots")
    op.drop_table("appointment_slots")
