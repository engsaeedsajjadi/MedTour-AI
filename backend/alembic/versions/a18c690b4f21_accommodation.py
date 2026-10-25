"""Section 18 accommodation records; revision a18c690b4f21; revises a17e526a13c9."""
from alembic import op
import sqlalchemy as sa
revision = "a18c690b4f21"
down_revision = "a17e526a13c9"
branch_labels = None
depends_on = None

def common():
    return [
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]

def upgrade():
    op.create_table("accommodation_properties", *common(),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False))
    op.create_index("ix_accommodation_properties_tenant_id", "accommodation_properties", ["tenant_id"])
    op.create_table("accommodation_inventory", *common(),
        sa.Column("property_id", sa.String(36), sa.ForeignKey("accommodation_properties.id"), nullable=False),
        sa.Column("room_type", sa.String(24), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("proposed_rooms", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False))
    op.create_index("ix_accommodation_inventory_tenant_id", "accommodation_inventory", ["tenant_id"])
    op.create_index("idx_accommodation_inventory_windows", "accommodation_inventory",
        ["tenant_id", "property_id", "room_type", "starts_on", "ends_on"])
    op.create_table("accommodation_stays", *common(),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("property_id", sa.String(36), sa.ForeignKey("accommodation_properties.id"), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("room_type", sa.String(24), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("rooms_requested", sa.Integer(), nullable=False),
        sa.Column("guests", sa.Integer(), nullable=False),
        sa.Column("inventory_id", sa.String(36), sa.ForeignKey("accommodation_inventory.id"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("internal_reference", sa.String(100), nullable=True),
        sa.Column("supplier_name", sa.String(100), nullable=True),
        sa.Column("supplier_reference", sa.String(100), nullable=True),
        sa.UniqueConstraint("tenant_id", "case_id", "request_key"))
    op.create_index("ix_accommodation_stays_tenant_id", "accommodation_stays", ["tenant_id"])
    op.create_index("idx_accommodation_stay_allocation", "accommodation_stays",
        ["tenant_id", "property_id", "inventory_id", "status", "starts_on", "ends_on"])
    op.create_table("accommodation_events", *common(),
        sa.Column("stay_id", sa.String(36), sa.ForeignKey("accommodation_stays.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("step_key", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("old_status", sa.String(40), nullable=False),
        sa.Column("new_status", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "stay_id", "step_key"))
    op.create_index("ix_accommodation_events_tenant_id", "accommodation_events", ["tenant_id"])

def downgrade():
    op.drop_index("ix_accommodation_events_tenant_id", table_name="accommodation_events")
    op.drop_table("accommodation_events")
    op.drop_index("idx_accommodation_stay_allocation", table_name="accommodation_stays")
    op.drop_index("ix_accommodation_stays_tenant_id", table_name="accommodation_stays")
    op.drop_table("accommodation_stays")
    op.drop_index("idx_accommodation_inventory_windows", table_name="accommodation_inventory")
    op.drop_index("ix_accommodation_inventory_tenant_id", table_name="accommodation_inventory")
    op.drop_table("accommodation_inventory")
    op.drop_index("ix_accommodation_properties_tenant_id", table_name="accommodation_properties")
    op.drop_table("accommodation_properties")
