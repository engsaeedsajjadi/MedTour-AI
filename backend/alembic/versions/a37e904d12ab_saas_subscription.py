"""Section 37 internal tenant subscriptions; no payment settlement."""
from alembic import op
import sqlalchemy as sa
revision="a37e904d12ab"
down_revision="a27e793f06b1"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("tenant_subscriptions",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("plan_code",sa.String(32),nullable=False),
        sa.Column("status",sa.String(24),nullable=False),
        sa.Column("granted_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.UniqueConstraint("tenant_id",name="uq_tenant_subscription"),
        sa.UniqueConstraint("tenant_id","id",name="uq_tenant_subscriptions_tenant_id"))
    op.create_index("ix_tenant_subscriptions_tenant_id","tenant_subscriptions",["tenant_id"])
    op.execute("""ALTER TABLE public.tenant_subscriptions
        ADD CONSTRAINT fk37_subscription_granter
        FOREIGN KEY (tenant_id,granted_by) REFERENCES public.users(tenant_id,id)
        DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""CREATE POLICY mt26_principal_isolation ON public.tenant_subscriptions
        FOR ALL TO PUBLIC USING (tenant_id=medtour_principal_private.tenant_for_login())
        WITH CHECK (tenant_id=medtour_principal_private.tenant_for_login())""")
def downgrade():
    op.execute("DROP POLICY mt26_principal_isolation ON public.tenant_subscriptions")
    op.drop_index("ix_tenant_subscriptions_tenant_id",table_name="tenant_subscriptions")
    op.drop_table("tenant_subscriptions")
