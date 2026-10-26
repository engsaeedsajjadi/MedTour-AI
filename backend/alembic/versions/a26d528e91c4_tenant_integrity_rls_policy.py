"""Section 26: tenant FK integrity and non-activated RLS principal guardrails.

This migration is intentionally SAFE on the legacy development instance.
It installs auditable tenant-aware composite FKs, and prepares a protected
principal mapping and deny-by-default policies, but DOES NOT ENABLE RLS on
live tables. Live app.main still uses the shared DATABASE_URL and legacy
opaque pre-auth tokens. Turning RLS on before separately provisioned
tenant-specific roles and routing would break existing endpoints.
RLS is exercised with real restricted users in ephemeral PostgreSQL CI.
"""
from __future__ import annotations
import hashlib
from alembic import op
import sqlalchemy as sa

revision="a26d528e91c4"
down_revision="a25e720d9b10"
branch_labels=None
depends_on=None

def q(value:str)->str:
    return '"' + value.replace('"','""') + '"'

def name(prefix:str,value:str)->str:
    return prefix+hashlib.sha256(value.encode()).hexdigest()[:18]

def children(conn):
    return conn.execute(sa.text("""
        SELECT child.relname AS child_table,parent.relname AS parent_table,
               ca.attname AS child_column,pa.attname AS parent_column,
               fk.conname AS original_constraint
        FROM pg_constraint fk
        JOIN pg_class child ON child.oid=fk.conrelid
        JOIN pg_namespace cn ON cn.oid=child.relnamespace
        JOIN pg_class parent ON parent.oid=fk.confrelid
        JOIN pg_namespace pn ON pn.oid=parent.relnamespace
        JOIN pg_attribute ca ON ca.attrelid=fk.conrelid AND ca.attnum=fk.conkey[1]
        JOIN pg_attribute pa ON pa.attrelid=fk.confrelid AND pa.attnum=fk.confkey[1]
        WHERE fk.contype='f' AND cn.nspname='public' AND pn.nspname='public'
          AND array_length(fk.conkey,1)=1 AND array_length(fk.confkey,1)=1
          AND EXISTS(SELECT 1 FROM pg_attribute att WHERE att.attrelid=child.oid
            AND att.attname='tenant_id' AND NOT att.attisdropped)
          AND EXISTS(SELECT 1 FROM pg_attribute att WHERE att.attrelid=parent.oid
            AND att.attname='tenant_id' AND NOT att.attisdropped)
        ORDER BY child.relname,ca.attname
    """)).mappings().all()

def tenant_tables(conn):
    return conn.execute(sa.text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE n.nspname='public' AND c.relkind IN ('r','p')
          AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname
    """)).scalars().all()

def upgrade():
    conn=op.get_bind()
    if conn.dialect.name!="postgresql":
        raise RuntimeError("Section 26 tenant-RLS migration requires PostgreSQL")
    conn.execute(sa.text("SET LOCAL lock_timeout='4s'"))
    tables=tenant_tables(conn)
    if len(tables)<37:
        raise RuntimeError("Tenant schema drift: expected >=37 tenant-owned tables")
    fks=children(conn)
    if len(fks)<48:
        raise RuntimeError("Tenant FK schema drift: expected >=48 links")
    if any(fk["parent_column"]!="id" for fk in fks):
        raise RuntimeError("Unreviewed multi-tenant reference target")
    # Verify existing row tenancy BEFORE installing constraints or permissions.
    for fk in fks:
        child=q(fk["child_table"]);parent=q(fk["parent_table"])
        col=q(fk["child_column"])
        mismatch=conn.execute(sa.text(f"""
            SELECT EXISTS(SELECT 1 FROM public.{child} AS c
                JOIN public.{parent} AS p ON c.{col}=p.id
                WHERE c.{col} IS NOT NULL AND c.tenant_id<>p.tenant_id LIMIT 1)
        """)).scalar()
        if mismatch:
            raise RuntimeError("Cross-tenant historical FK data detected: migration denied")
    # Stable unique pair is required to reference tenant_id + id.
    for table in tables:
        unique_name=name("mt26_uq_",table)
        conn.execute(sa.text(f"""
            ALTER TABLE public.{q(table)} ADD CONSTRAINT {q(unique_name)}
            UNIQUE (tenant_id,id)
        """))
    for fk in fks:
        table=q(fk["child_table"]);parent=q(fk["parent_table"])
        col=q(fk["child_column"])
        label=name("mt26_fk_",fk["child_table"]+"|"+fk["child_column"]+"|"+fk["parent_table"])
        # Leave the original FK intact to preserve ON DELETE/UPDATE semantics.
        # Deferred NO ACTION checks the final transaction state after cascades.
        conn.execute(sa.text(f"""
            ALTER TABLE public.{table}
             ADD CONSTRAINT {q(label)}
             FOREIGN KEY (tenant_id,{col})
             REFERENCES public.{parent} (tenant_id,id)
             DEFERRABLE INITIALLY DEFERRED
        """))
    # SECURITY DEFINER uses *authenticated session_user*, not forgeable GUCs.
    # No public grants, no provisioning of login roles, no magic fallback.
    conn.execute(sa.text("""
        CREATE SCHEMA IF NOT EXISTS medtour_principal_private
    """))
    conn.execute(sa.text("""
        REVOKE ALL ON SCHEMA medtour_principal_private FROM PUBLIC
    """))
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS medtour_principal_private.role_tenant_mapping(
          database_role name PRIMARY KEY,
          tenant_id varchar(36) NOT NULL UNIQUE REFERENCES public.tenants(id)
        )
    """))
    conn.execute(sa.text("""
        REVOKE ALL ON TABLE medtour_principal_private.role_tenant_mapping FROM PUBLIC
    """))
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION medtour_principal_private.tenant_for_login()
        RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path=pg_catalog, medtour_principal_private
        AS $$
          SELECT m.tenant_id::text
          FROM medtour_principal_private.role_tenant_mapping AS m
          WHERE m.database_role=session_user
        $$
    """))
    conn.execute(sa.text("""
        REVOKE ALL ON FUNCTION medtour_principal_private.tenant_for_login() FROM PUBLIC
    """))
    for table in tables:
        # Policy exists, but will be applied ONLY AFTER separate role routing.
        # Unmapped/legacy roles fail closed once RLS is activated.
        conn.execute(sa.text(f"""
            CREATE POLICY mt26_principal_isolation ON public.{q(table)}
            FOR ALL TO PUBLIC
            USING (tenant_id = medtour_principal_private.tenant_for_login())
            WITH CHECK (tenant_id = medtour_principal_private.tenant_for_login())
        """))
    # NOTE: no ALTER TABLE ... ENABLE RLS or FORCE RLS in this migration.
    # No GRANT or runtime role activation occurs here.

def downgrade():
    conn=op.get_bind()
    if conn.dialect.name!="postgresql":
        raise RuntimeError("PostgreSQL required")
    # Refuse downgrading any database where live RLS may have been activated.
    for table in tenant_tables(conn):
        state=conn.execute(sa.text("""
          SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname=:name
        """),{"name":table}).scalar()
        if state:raise RuntimeError("Refusing downgrade: active tenant RLS needs explicit rollback plan")
    for fk in children(conn):
        name_fk=name("mt26_fk_",fk["child_table"]+"|"+fk["child_column"]+"|"+fk["parent_table"])
        conn.execute(sa.text(f"""
            ALTER TABLE public.{q(fk["child_table"])} DROP CONSTRAINT IF EXISTS {q(name_fk)}
        """))
    for table in tenant_tables(conn):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS mt26_principal_isolation ON public.{q(table)}"))
        conn.execute(sa.text(f"""
            ALTER TABLE public.{q(table)} DROP CONSTRAINT IF EXISTS {q(name("mt26_uq_",table))}
        """))
    conn.execute(sa.text("DROP FUNCTION medtour_principal_private.tenant_for_login()"))
    conn.execute(sa.text("DROP TABLE medtour_principal_private.role_tenant_mapping"))
    conn.execute(sa.text("DROP SCHEMA medtour_principal_private"))
