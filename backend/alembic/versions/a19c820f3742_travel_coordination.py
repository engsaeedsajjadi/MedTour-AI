"""Section 19 transport/interpreter coordination; revision a19c820f3742."""
from alembic import op
import sqlalchemy as sa

revision="a19c820f3742"
down_revision="a18c690b4f21"
branch_labels=None
depends_on=None

def cols():
    return [sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
            sa.Column("id",sa.String(36),primary_key=True,nullable=False),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False)]

def upgrade():
    op.create_table("travel_resources",*cols(),
        sa.Column("kind",sa.String(24),nullable=False),
        sa.Column("label",sa.String(120),nullable=False),
        sa.Column("city",sa.String(80),nullable=False),
        sa.Column("seats",sa.Integer(),nullable=False),
        sa.Column("language",sa.String(10),nullable=True),
        sa.Column("status",sa.String(24),nullable=False),
        sa.Column("recorded_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False))
    op.create_index("ix_travel_resources_tenant_id","travel_resources",["tenant_id"])
    op.create_table("travel_resource_windows",*cols(),
        sa.Column("resource_id",sa.String(36),sa.ForeignKey("travel_resources.id"),nullable=False),
        sa.Column("starts_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("ends_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("reference",sa.String(100),nullable=False),
        sa.Column("status",sa.String(24),nullable=False),
        sa.Column("recorded_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False))
    op.create_index("ix_travel_resource_windows_tenant_id","travel_resource_windows",["tenant_id"])
    op.create_index("idx_travel_windows_resource","travel_resource_windows",["tenant_id","resource_id","starts_at"])
    op.create_table("travel_assignments",*cols(),
        sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),
        sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("resource_id",sa.String(36),sa.ForeignKey("travel_resources.id"),nullable=False),
        sa.Column("request_key",sa.String(100),nullable=False),
        sa.Column("kind",sa.String(40),nullable=False),
        sa.Column("starts_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("ends_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("passengers",sa.Integer(),nullable=False),
        sa.Column("language",sa.String(10),nullable=True),
        sa.Column("origin_zone",sa.String(30),nullable=False),
        sa.Column("destination_zone",sa.String(30),nullable=False),
        sa.Column("window_id",sa.String(36),sa.ForeignKey("travel_resource_windows.id"),nullable=True),
        sa.Column("status",sa.String(40),nullable=False),
        sa.Column("reference",sa.String(100),nullable=True),
        sa.Column("supplier_name",sa.String(100),nullable=True),
        sa.Column("supplier_reference",sa.String(100),nullable=True),
        sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.UniqueConstraint("tenant_id","case_id","request_key"))
    op.create_index("ix_travel_assignments_tenant_id","travel_assignments",["tenant_id"])
    op.create_index("idx_travel_assignment_resource","travel_assignments",["tenant_id","resource_id","status","starts_at","ends_at"])
    op.create_table("travel_assignment_events",*cols(),
        sa.Column("request_id",sa.String(36),sa.ForeignKey("travel_assignments.id"),nullable=False),
        sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("step_key",sa.String(100),nullable=False),
        sa.Column("fingerprint",sa.String(64),nullable=False),
        sa.Column("action",sa.String(40),nullable=False),
        sa.Column("old_status",sa.String(40),nullable=False),
        sa.Column("new_status",sa.String(40),nullable=False),
        sa.Column("reference",sa.String(100),nullable=False),
        sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("tenant_id","request_id","step_key"))
    op.create_index("ix_travel_assignment_events_tenant_id","travel_assignment_events",["tenant_id"])

def downgrade():
    op.drop_index("ix_travel_assignment_events_tenant_id",table_name="travel_assignment_events")
    op.drop_table("travel_assignment_events")
    op.drop_index("idx_travel_assignment_resource",table_name="travel_assignments")
    op.drop_index("ix_travel_assignments_tenant_id",table_name="travel_assignments")
    op.drop_table("travel_assignments")
    op.drop_index("idx_travel_windows_resource",table_name="travel_resource_windows")
    op.drop_index("ix_travel_resource_windows_tenant_id",table_name="travel_resource_windows")
    op.drop_table("travel_resource_windows")
    op.drop_index("ix_travel_resources_tenant_id",table_name="travel_resources")
    op.drop_table("travel_resources")
