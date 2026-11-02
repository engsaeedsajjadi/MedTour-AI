"""Section 27: staff authentication version, encrypted TOTP and login challenges.

Does not activate MFA for existing accounts automatically; no tokens or secrets
are migrated into user-visible artifacts.
"""
from alembic import op
import sqlalchemy as sa
revision="a27f159d6821"
down_revision="a27e793f06b1"
branch_labels=None
depends_on=None

def common():
    return [sa.Column("id",sa.String(36),primary_key=True),
            sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False)]
def upgrade():
    op.add_column("users",sa.Column("auth_version",sa.Integer(),server_default="0",nullable=False))
    op.add_column("refresh_sessions",sa.Column("mfa_verified",sa.Boolean(),
        server_default=sa.false(),nullable=False))
    op.create_table("staff_totp",*common(),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("encrypted_secret",sa.Text(),nullable=False),
        sa.Column("enabled",sa.Boolean(),server_default=sa.false(),nullable=False),
        sa.Column("setup_expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("last_step",sa.Integer(),server_default="-1",nullable=False),
        sa.UniqueConstraint("tenant_id","user_id"))
    op.create_index("ix_staff_totp_tenant_id","staff_totp",["tenant_id"])
    op.create_table("staff_mfa_challenges",*common(),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("challenge_hash",sa.String(64),nullable=False,unique=True),
        sa.Column("auth_version",sa.Integer(),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("attempts",sa.Integer(),server_default="0",nullable=False),
        sa.Column("used_at",sa.DateTime(timezone=True)),
    )
    op.create_index("ix_staff_mfa_challenges_tenant_id","staff_mfa_challenges",["tenant_id"])
    op.create_index("ix_staff_mfa_tenant_account","staff_mfa_challenges",["tenant_id","user_id"])
    if op.get_bind().dialect.name=="postgresql":
        op.execute("ALTER TABLE staff_totp ADD CONSTRAINT mt27_totp_tenant_user_fk FOREIGN KEY (tenant_id,user_id) REFERENCES users (tenant_id,id) DEFERRABLE INITIALLY DEFERRED")
        op.execute("ALTER TABLE staff_mfa_challenges ADD CONSTRAINT mt27_challenge_tenant_user_fk FOREIGN KEY (tenant_id,user_id) REFERENCES users (tenant_id,id) DEFERRABLE INITIALLY DEFERRED")
        for table in ("staff_totp","staff_mfa_challenges"):
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT mt27_{table}_tenant_id_unique UNIQUE (tenant_id,id)")
            op.execute(f"CREATE POLICY mt26_principal_isolation ON {table} FOR ALL TO PUBLIC USING (tenant_id=medtour_principal_private.tenant_for_login()) WITH CHECK (tenant_id=medtour_principal_private.tenant_for_login())")
            # No live RLS activation; same safety contract as Section 26.
def downgrade():
    op.drop_index("ix_staff_mfa_tenant_account",table_name="staff_mfa_challenges")
    op.drop_index("ix_staff_mfa_challenges_tenant_id",table_name="staff_mfa_challenges")
    op.drop_table("staff_mfa_challenges")
    op.drop_index("ix_staff_totp_tenant_id",table_name="staff_totp")
    op.drop_table("staff_totp")
    op.drop_column("refresh_sessions","mfa_verified")
    op.drop_column("users","auth_version")
