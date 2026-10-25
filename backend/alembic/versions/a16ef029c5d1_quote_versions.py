"""Section 16 versioned quotes. Revision a16ef029c5d1, parent a15c18e2674b."""
from alembic import op
import sqlalchemy as sa
revision="a16ef029c5d1"
down_revision="a15c18e2674b"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("quote_versions",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("quote_id",sa.String(36),sa.ForeignKey("quotes.id"),nullable=False),
        sa.Column("case_id",sa.String(36),sa.ForeignKey("cases.id"),nullable=False),
        sa.Column("version",sa.Integer(),nullable=False),
        sa.Column("currency",sa.String(3),nullable=False),
        sa.Column("lines_json",sa.Text(),nullable=False),
        sa.Column("total_minor",sa.BigInteger(),nullable=False),
        sa.Column("status",sa.String(32),nullable=False),
        sa.Column("created_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("approval_reference",sa.String(100),nullable=True),
        sa.UniqueConstraint("tenant_id","quote_id","version"),
    )
    op.create_index("ix_quote_versions_tenant_id","quote_versions",["tenant_id"])
    op.create_index("ix_quote_versions_quote_id","quote_versions",["quote_id"])

def downgrade():
    op.drop_index("ix_quote_versions_quote_id",table_name="quote_versions")
    op.drop_index("ix_quote_versions_tenant_id",table_name="quote_versions")
    op.drop_table("quote_versions")
