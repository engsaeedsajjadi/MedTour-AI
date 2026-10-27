"""Section 28 privacy request registry; policies created but production RLS activation is external."""
from alembic import op
import sqlalchemy as sa
revision="a28f406c12de"
down_revision="a27f159d6821"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("privacy_requests",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("patient_id",sa.String(36),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("request_type",sa.String(24),nullable=False),
        sa.Column("status",sa.String(24),nullable=False),
        sa.Column("requested_by",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("reviewed_by",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.UniqueConstraint("tenant_id","id",name="mt28_uq_privacy_requests"))
    op.create_index("ix_privacy_requests_tenant_id","privacy_requests",["tenant_id"])
    for column,parent in [("patient_id","patients"),("requested_by","users"),("reviewed_by","users")]:
        op.execute(f"""ALTER TABLE public.privacy_requests ADD CONSTRAINT mt28_fk_privacy_{column}
            FOREIGN KEY (tenant_id,{column}) REFERENCES public.{parent}(tenant_id,id)
            DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""CREATE POLICY mt26_principal_isolation ON public.privacy_requests
        FOR ALL TO PUBLIC USING (tenant_id=medtour_principal_private.tenant_for_login())
        WITH CHECK (tenant_id=medtour_principal_private.tenant_for_login())""")

def downgrade():
    op.execute("DROP POLICY mt26_principal_isolation ON public.privacy_requests")
    op.drop_index("ix_privacy_requests_tenant_id",table_name="privacy_requests")
    op.drop_table("privacy_requests")
