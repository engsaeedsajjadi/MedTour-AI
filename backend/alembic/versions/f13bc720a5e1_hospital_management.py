"""Section 13 hospital coordination (metadata only).

Revision ID: f13bc720a5e1
Revises: e12c97f30a2d
"""
from alembic import op
import sqlalchemy as sa

revision = "f13bc720a5e1"
down_revision = "e12c97f30a2d"
branch_labels = None
depends_on = None

def basic():
    return [
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]

def upgrade():
    op.create_table("hospital_accounts", *basic(),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("linked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tenant_id", "hospital_id", "user_id"),
        sa.UniqueConstraint("tenant_id", "user_id"))
    op.create_table("hospital_credentials", *basic(),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("issuing_country", sa.String(2), nullable=False),
        sa.Column("issuing_authority", sa.String(120), nullable=False),
        sa.Column("registration_reference", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "hospital_id"))
    op.create_table("hospital_services", *basic(),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("service_code", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("tenant_id", "hospital_id", "service_code"))
    op.create_table("hospital_capacity", *basic(),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("service_code", sa.String(48), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposed_units", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False))
    op.create_table("hospital_coordinations", *basic(),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("service_code", sa.String(48), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("last_actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("tenant_id", "hospital_id", "case_id", "reference"))
    for table, columns in {
        "hospital_accounts":["tenant_id", "hospital_id", "user_id"],
        "hospital_credentials":["tenant_id", "hospital_id"],
        "hospital_services":["tenant_id", "hospital_id"],
        "hospital_capacity":["tenant_id", "hospital_id"],
        "hospital_coordinations":["tenant_id", "hospital_id", "case_id"],
    }.items():
        for col in columns:
            op.create_index("ix_"+table+"_"+col, table, [col])
    op.create_index("idx_hospital_capacity_window", "hospital_capacity",
                    ["tenant_id", "hospital_id", "starts_at"])

def downgrade():
    op.drop_index("idx_hospital_capacity_window", table_name="hospital_capacity")
    for table, columns in reversed(list({
        "hospital_accounts":["tenant_id","hospital_id","user_id"],
        "hospital_credentials":["tenant_id","hospital_id"],
        "hospital_services":["tenant_id","hospital_id"],
        "hospital_capacity":["tenant_id","hospital_id"],
        "hospital_coordinations":["tenant_id","hospital_id","case_id"],
    }.items())):
        for col in reversed(columns):
            op.drop_index("ix_"+table+"_"+col, table_name=table)
        op.drop_table(table)
