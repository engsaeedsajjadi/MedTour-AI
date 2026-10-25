"""Section 20 administrative international-agent governance; after section 19."""
from alembic import op
import sqlalchemy as sa
revision="a20d781c4e63"
down_revision="a19c820f3742"
branch_labels=None
depends_on=None

def base():
    return [
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
    ]

def upgrade():
    op.create_table("agent_agreements",*base(),
        sa.Column("agent_id",sa.String(36),sa.ForeignKey("agents.id"),nullable=False),
        sa.Column("contract_key",sa.String(100),nullable=False),
        sa.Column("jurisdiction",sa.String(2),nullable=False),
        sa.Column("currency",sa.String(3),nullable=False),
        sa.Column("max_budget_minor",sa.BigInteger(),nullable=False),
        sa.Column("scope",sa.String(80),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("document_reference",sa.String(100),nullable=True),
        sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.UniqueConstraint("tenant_id","agent_id","contract_key"))
    op.create_index("ix_agent_agreements_tenant_id","agent_agreements",["tenant_id"])
    op.create_table("agent_identities",*base(),
        sa.Column("agent_id",sa.String(36),sa.ForeignKey("agents.id"),nullable=False),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("provisioned_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.UniqueConstraint("tenant_id","user_id"),sa.UniqueConstraint("tenant_id","agent_id"))
    op.create_index("ix_agent_identities_tenant_id","agent_identities",["tenant_id"])
    op.create_table("agent_referral_intents",*base(),
        sa.Column("agent_id",sa.String(36),sa.ForeignKey("agents.id"),nullable=False),
        sa.Column("agreement_id",sa.String(36),sa.ForeignKey("agent_agreements.id"),nullable=False),
        sa.Column("request_key",sa.String(100),nullable=False),
        sa.Column("channel",sa.String(30),nullable=False),
        sa.Column("campaign_code",sa.String(60),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=True),
        sa.Column("matched_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.UniqueConstraint("tenant_id","agent_id","request_key"),
        sa.UniqueConstraint("tenant_id","patient_id"))
    op.create_index("ix_agent_referral_intents_tenant_id","agent_referral_intents",["tenant_id"])
    op.create_index("idx_agent_intents_by_agent","agent_referral_intents",["tenant_id","agent_id","status"])
    op.create_table("agent_commercial_drafts",*base(),
        sa.Column("agent_id",sa.String(36),sa.ForeignKey("agents.id"),nullable=False),
        sa.Column("agreement_id",sa.String(36),sa.ForeignKey("agent_agreements.id"),nullable=False),
        sa.Column("draft_key",sa.String(100),nullable=False),
        sa.Column("activity_reference",sa.String(100),nullable=False),
        sa.Column("amount_minor",sa.BigInteger(),nullable=False),
        sa.Column("status",sa.String(48),nullable=False),
        sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.UniqueConstraint("tenant_id","agent_id","draft_key"))
    op.create_index("ix_agent_commercial_drafts_tenant_id","agent_commercial_drafts",["tenant_id"])
    op.create_table("agent_governance_events",*base(),
        sa.Column("agent_id",sa.String(36),sa.ForeignKey("agents.id"),nullable=False),
        sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("entity_kind",sa.String(40),nullable=False),
        sa.Column("entity_id",sa.String(36),nullable=False),
        sa.Column("action",sa.String(48),nullable=False),
        sa.Column("reference",sa.String(100),nullable=False))
    op.create_index("ix_agent_governance_events_tenant_id","agent_governance_events",["tenant_id"])

def downgrade():
    for name in ("agent_governance_events","agent_commercial_drafts",
                 "agent_referral_intents","agent_identities","agent_agreements"):
        op.drop_index("ix_"+name+"_tenant_id",table_name=name)
        if name=="agent_referral_intents":
            op.drop_index("idx_agent_intents_by_agent",table_name=name)
        op.drop_table(name)
