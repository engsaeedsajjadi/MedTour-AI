"""Section 24: consent-safe administrative AI orchestration metadata.

Never backfill prompts or PHI. The administrative run keeps bounded,
non-sensitive display text only and no patient/case or external delivery link.
"""
from alembic import op
import sqlalchemy as sa
revision="a24f703c9b62"
down_revision="a23e674c5b20"
branch_labels=None
depends_on=None

def cols():
    return [
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
    ]
def upgrade():
    op.create_table("ai_agent_policies",*cols(),
        sa.Column("agent_key",sa.String(60),nullable=False),
        sa.Column("enabled",sa.Boolean(),nullable=False),
        sa.Column("provider_mode",sa.String(25),nullable=False),
        sa.Column("daily_run_limit",sa.Integer(),nullable=False),
        sa.Column("updated_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.UniqueConstraint("tenant_id","agent_key"))
    op.create_index("ix_ai_agent_policies_tenant_id","ai_agent_policies",["tenant_id"])
    op.create_table("ai_orchestration_runs",*cols(),
        sa.Column("request_key",sa.String(100),nullable=False),
        sa.Column("agent_key",sa.String(60),nullable=False),
        sa.Column("workflow",sa.String(60),nullable=False),
        sa.Column("locale",sa.String(10),nullable=False),
        sa.Column("input_hash",sa.String(64),nullable=False),
        sa.Column("status",sa.String(40),nullable=False),
        sa.Column("mode",sa.String(25),nullable=False),
        sa.Column("result_text",sa.Text(),nullable=False),
        sa.Column("knowledge_ids_json",sa.Text(),nullable=False),
        sa.Column("authored_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("reviewer_id",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("decision_reference",sa.String(100),nullable=True),
        sa.UniqueConstraint("tenant_id","request_key"))
    op.create_index("ix_ai_orchestration_runs_tenant_id","ai_orchestration_runs",["tenant_id"])
    op.create_index("ix_ai_orchestration_tenant_state","ai_orchestration_runs",["tenant_id","status","created_at"])
    op.create_table("ai_orchestration_events",*cols(),
        sa.Column("run_id",sa.String(36),sa.ForeignKey("ai_orchestration_runs.id"),nullable=False),
        sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("action",sa.String(80),nullable=False),
        sa.Column("detail_code",sa.String(80),nullable=False))
    op.create_index("ix_ai_orchestration_events_tenant_id","ai_orchestration_events",["tenant_id"])
    op.create_index("ix_ai_orchestration_events_run","ai_orchestration_events",["tenant_id","run_id","created_at"])
def downgrade():
    op.drop_index("ix_ai_orchestration_events_run",table_name="ai_orchestration_events")
    op.drop_index("ix_ai_orchestration_events_tenant_id",table_name="ai_orchestration_events")
    op.drop_table("ai_orchestration_events")
    op.drop_index("ix_ai_orchestration_tenant_state",table_name="ai_orchestration_runs")
    op.drop_index("ix_ai_orchestration_runs_tenant_id",table_name="ai_orchestration_runs")
    op.drop_table("ai_orchestration_runs")
    op.drop_index("ix_ai_agent_policies_tenant_id",table_name="ai_agent_policies")
    op.drop_table("ai_agent_policies")
