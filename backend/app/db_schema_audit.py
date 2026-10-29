"""Section 32: read-only PostgreSQL multi-tenancy schema audit.

Never repairs schema, enables RLS, reads row-level patient data or exposes credentials.
Requires a dedicated read-only catalog inspection connection.
"""
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import text

CATALOG_SQL = """
WITH tenant_tables AS (
 SELECT c.oid, n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE n.nspname='public' AND c.relkind IN ('r','p') AND
 a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
)
SELECT t.relname AS table_name,
 t.relrowsecurity AS rls_enabled,
 t.relforcerowsecurity AS rls_forced,
 EXISTS (
  SELECT 1 FROM pg_policies p WHERE p.schemaname='public'
  AND p.tablename=t.relname AND p.policyname='mt26_principal_isolation'
 ) AS has_principal_policy,
 EXISTS (
  SELECT 1 FROM pg_constraint con WHERE con.conrelid=t.oid
  AND con.contype='u' AND (
   SELECT array_agg(a.attname ORDER BY a.attname)
   FROM unnest(con.conkey) AS k(attnum)
   JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
  )=ARRAY['id','tenant_id']::name[]
 ) AS tenant_id_unique
FROM tenant_tables t ORDER BY t.relname
"""

FK_SQL = """
SELECT child.relname AS child_table, parent.relname AS parent_table,
 a.attname AS fk_column,
 EXISTS (
  SELECT 1 FROM pg_constraint composite
  JOIN pg_class p2 ON p2.oid=composite.confrelid
  WHERE composite.conrelid=fk.conrelid AND composite.contype='f'
   AND p2.oid=parent.oid AND array_length(composite.conkey,1)=2
   AND array_length(composite.confkey,1)=2
   AND EXISTS (
    SELECT 1 FROM unnest(composite.conkey) x(n)
    JOIN pg_attribute z ON z.attrelid=child.oid AND z.attnum=x.n
    WHERE z.attname='tenant_id'
   )
   AND EXISTS (
    SELECT 1 FROM unnest(composite.conkey) x(n)
    JOIN pg_attribute z ON z.attrelid=child.oid AND z.attnum=x.n
    WHERE z.attname=a.attname
   )
   AND EXISTS (
    SELECT 1 FROM unnest(composite.confkey) x(n)
    JOIN pg_attribute z ON z.attrelid=parent.oid AND z.attnum=x.n
    WHERE z.attname='tenant_id'
   )
  ) AS has_tenant_fk
FROM pg_constraint fk
JOIN pg_class child ON child.oid=fk.conrelid
JOIN pg_namespace cn ON cn.oid=child.relnamespace
JOIN pg_class parent ON parent.oid=fk.confrelid
JOIN pg_namespace pn ON pn.oid=parent.relnamespace
JOIN pg_attribute a ON a.attrelid=child.oid AND a.attnum=fk.conkey[1]
WHERE fk.contype='f' AND cn.nspname='public' AND pn.nspname='public'
 AND array_length(fk.conkey,1)=1 AND array_length(fk.confkey,1)=1
 AND EXISTS(SELECT 1 FROM pg_attribute x WHERE x.attrelid=child.oid AND x.attname='tenant_id')
 AND EXISTS(SELECT 1 FROM pg_attribute x WHERE x.attrelid=parent.oid AND x.attname='tenant_id')
ORDER BY child.relname,a.attname
"""

def assess(tables:list[dict],fks:list[dict])->dict:
    """Fail closed. The report uses catalog metadata, never live patient rows."""
    faults=[]
    if not tables:faults.append("no_tenant_tables")
    for t in tables:
        name=t["table_name"]
        for field,code in (
            ("has_principal_policy","missing_principal_policy"),
            ("tenant_id_unique","missing_tenant_unique"),
            ("rls_enabled","rls_not_enabled"),
            ("rls_forced","rls_not_forced"),
        ):
            if not t[field]:faults.append(f"{code}:{name}")
    for fk in fks:
        if not fk["has_tenant_fk"]:
            faults.append(f"missing_composite_tenant_fk:{fk['child_table']}:{fk['fk_column']}")
    return {"schema_review_passed":not faults,"tenant_table_count":len(tables),
            "legacy_single_column_fk_count":len(fks),"findings":faults,
            "runtime_tenant_routing_verified":False,
            "production_authorized":False}

def inspect(connection)->dict:
    if connection.dialect.name!="postgresql":
        raise RuntimeError("PostgreSQL required for Section 32 catalog audit")
    tables=[dict(x) for x in connection.execute(text(CATALOG_SQL)).mappings()]
    fks=[dict(x) for x in connection.execute(text(FK_SQL)).mappings()]
    return assess(tables,fks)
