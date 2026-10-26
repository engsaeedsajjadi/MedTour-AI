"""Section 27 staff MFA and doctor grants. Sensitive secrets never returned after setup."""
from alembic import op
import sqlalchemy as sa
revision="a27e793f06b1"
down_revision="a26d528e91c4"
branch_labels=None
depends_on=None

def base():
    return [sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False)]

def upgrade():
    op.create_table("staff_mfa",*base(),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("secret_encrypted",sa.Text(),nullable=False),
        sa.Column("enabled",sa.Boolean(),nullable=False),
        sa.Column("last_counter",sa.BigInteger(),nullable=False),
        sa.UniqueConstraint("tenant_id","user_id"))
    op.create_index("ix_staff_mfa_tenant_id","staff_mfa",["tenant_id"])
    op.create_table("doctor_case_grants",*base(),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),
        sa.Column("granted_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("revoked_at",sa.DateTime(timezone=True),nullable=True),
        sa.UniqueConstraint("tenant_id","user_id","case_id"))
    op.create_index("ix_doctor_case_grants_tenant_id","doctor_case_grants",["tenant_id"])
    op.create_index("ix_doctor_case_grants_case_id","doctor_case_grants",["case_id"])
def downgrade():
    op.drop_index("ix_doctor_case_grants_case_id",table_name="doctor_case_grants")
    op.drop_index("ix_doctor_case_grants_tenant_id",table_name="doctor_case_grants")
    op.drop_table("doctor_case_grants")
    op.drop_index("ix_staff_mfa_tenant_id",table_name="staff_mfa")
    op.drop_table("staff_mfa")
