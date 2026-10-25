"""Section 21: patient portal one-time invitations; revises section 20."""
from alembic import op
import sqlalchemy as sa
revision="a21c493b5e70"
down_revision="a20d781c4e63"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("portal_login_challenges",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("invitation_hash",sa.String(64),unique=True,nullable=False),
        sa.Column("code_hash",sa.String(64),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("attempts",sa.Integer(),nullable=False),
        sa.Column("consumed_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("issued_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
    )
    op.create_index("ix_portal_login_challenges_tenant_id","portal_login_challenges",["tenant_id"])
    op.create_index("idx_portal_login_patient","portal_login_challenges",["tenant_id","patient_id","expires_at"])
    # Invalidate any old bearer-only sessions that predate challenge verification.
    op.execute("UPDATE portal_access SET revoked = TRUE WHERE revoked = FALSE")

def downgrade():
    op.drop_index("idx_portal_login_patient",table_name="portal_login_challenges")
    op.drop_index("ix_portal_login_challenges_tenant_id",table_name="portal_login_challenges")
    op.drop_table("portal_login_challenges")
