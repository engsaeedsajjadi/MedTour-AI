"""Section 11 human inbox.

Revision ID: d11ab47302c1
Revises: c9d093e78a21
"""
from alembic import op
import sqlalchemy as sa

revision="d11ab47302c1"
down_revision="c9d093e78a21"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table(
        "inbox_threads",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("conversation_id",sa.String(36),sa.ForeignKey("conversations.id"),nullable=False),
        sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("status",sa.String(24),nullable=False),
        sa.Column("priority",sa.String(16),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("tenant_id","conversation_id"),
    )
    op.create_index("ix_inbox_threads_tenant_id","inbox_threads",["tenant_id"])
    op.create_index("ix_inbox_threads_conversation_id","inbox_threads",["conversation_id"])
    op.create_index("idx_inbox_queue","inbox_threads",["tenant_id","status","priority"])
    op.create_table(
        "inbox_actions",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("conversation_id",sa.String(36),sa.ForeignKey("conversations.id"),nullable=False),
        sa.Column("actor_user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("action",sa.String(40),nullable=False),
        sa.Column("from_status",sa.String(24),nullable=False),
        sa.Column("to_status",sa.String(24),nullable=False),
        sa.Column("target_user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
    )
    op.create_index("ix_inbox_actions_tenant_id","inbox_actions",["tenant_id"])
    op.create_index("ix_inbox_actions_conversation_id","inbox_actions",["conversation_id"])

def downgrade():
    op.drop_index("ix_inbox_actions_conversation_id",table_name="inbox_actions")
    op.drop_index("ix_inbox_actions_tenant_id",table_name="inbox_actions")
    op.drop_table("inbox_actions")
    op.drop_index("idx_inbox_queue",table_name="inbox_threads")
    op.drop_index("ix_inbox_threads_conversation_id",table_name="inbox_threads")
    op.drop_index("ix_inbox_threads_tenant_id",table_name="inbox_threads")
    op.drop_table("inbox_threads")
