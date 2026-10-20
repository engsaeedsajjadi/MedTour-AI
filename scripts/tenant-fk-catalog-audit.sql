-- Read-only PostgreSQL 17 audit of tenant-scoped foreign keys.
-- This audit checks database constraints, not application queries or the existence of a data leak.
-- It does not modify any tables, roles, policies, or records.
\pset pager off
WITH fk_columns AS (
  SELECT
      con.oid AS constraint_oid,
      con.conname AS constraint_name,
      child.relname AS child_table,
      parent.relname AS parent_table,
      array_agg(child_att.attname ORDER BY u.ord) AS child_columns,
      array_agg(parent_att.attname ORDER BY u.ord) AS parent_columns,
      bool_or(child_att.attname = 'tenant_id' AND parent_att.attname = 'tenant_id') AS tenant_paired,
      EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = con.conrelid
          AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
      ) AS child_has_tenant,
      EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = con.confrelid
          AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
      ) AS parent_has_tenant
  FROM pg_constraint con
  JOIN pg_class child ON child.oid = con.conrelid
  JOIN pg_namespace ns ON ns.oid = child.relnamespace
  JOIN pg_class parent ON parent.oid = con.confrelid
  JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY
    AS u(child_attnum, parent_attnum, ord) ON TRUE
  JOIN pg_attribute child_att ON child_att.attrelid = con.conrelid
    AND child_att.attnum = u.child_attnum
  JOIN pg_attribute parent_att ON parent_att.attrelid = con.confrelid
    AND parent_att.attnum = u.parent_attnum
  WHERE con.contype = 'f' AND ns.nspname = 'public'
  GROUP BY con.oid, con.conname, con.conrelid, con.confrelid,
           child.relname, parent.relname
)
SELECT
  count(*) AS all_foreign_keys,
  count(*) FILTER (WHERE child_has_tenant AND parent_has_tenant)
    AS tenant_to_tenant_foreign_keys,
  count(*) FILTER (WHERE child_has_tenant AND parent_has_tenant AND tenant_paired)
    AS tenant_paired_foreign_keys,
  count(*) FILTER (WHERE child_has_tenant AND parent_has_tenant AND NOT tenant_paired)
    AS needs_tenant_pair_review
FROM fk_columns;

WITH fk_columns AS (
  SELECT
      con.conname AS constraint_name,
      child.relname AS child_table,
      parent.relname AS parent_table,
      string_agg(child_att.attname, ', ' ORDER BY u.ord) AS child_columns,
      string_agg(parent_att.attname, ', ' ORDER BY u.ord) AS parent_columns,
      bool_or(child_att.attname = 'tenant_id' AND parent_att.attname = 'tenant_id') AS tenant_paired,
      EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = con.conrelid
          AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
      ) AS child_has_tenant,
      EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = con.confrelid
          AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
      ) AS parent_has_tenant
  FROM pg_constraint con
  JOIN pg_class child ON child.oid = con.conrelid
  JOIN pg_namespace ns ON ns.oid = child.relnamespace
  JOIN pg_class parent ON parent.oid = con.confrelid
  JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY
    AS u(child_attnum, parent_attnum, ord) ON TRUE
  JOIN pg_attribute child_att ON child_att.attrelid = con.conrelid
    AND child_att.attnum = u.child_attnum
  JOIN pg_attribute parent_att ON parent_att.attrelid = con.confrelid
    AND parent_att.attnum = u.parent_attnum
  WHERE con.contype = 'f' AND ns.nspname = 'public'
  GROUP BY con.oid, con.conname, con.conrelid, con.confrelid,
           child.relname, parent.relname
)
SELECT
  child_table, child_columns, parent_table, parent_columns, constraint_name
FROM fk_columns
WHERE child_has_tenant AND parent_has_tenant AND NOT tenant_paired
ORDER BY child_table, parent_table, constraint_name;
