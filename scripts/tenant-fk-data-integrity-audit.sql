-- MedTour AI: read-only audit of existing cross-tenant foreign-key relationships.
-- PostgreSQL 17. This performs SELECTs against catalog and operational tables.
-- No INSERT/UPDATE/DELETE/ALTER/GRANT; output contains aggregated counts only.
-- Detects mismatches in rows linked through FK constraints; does NOT validate
-- every business-level association or implement tenant-safe constraints.
\pset pager off
\set ON_ERROR_STOP on

DO $tenant_fk_audit$
DECLARE
  fk record;
  mismatches bigint;
  checked integer := 0;
  affected integer := 0;
  total_mismatches bigint := 0;
BEGIN
  FOR fk IN
    SELECT
      con.conname AS constraint_name,
      child_ns.nspname AS child_schema,
      child.relname AS child_table,
      parent_ns.nspname AS parent_schema,
      parent.relname AS parent_table,
      string_agg(
        format('c.%I = p.%I', child_att.attname, parent_att.attname),
        ' AND ' ORDER BY cols.ord
      ) AS join_predicate
    FROM pg_constraint con
    JOIN pg_class child ON child.oid = con.conrelid
    JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
    JOIN pg_class parent ON parent.oid = con.confrelid
    JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
    JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY
      AS cols(child_attnum, parent_attnum, ord) ON true
    JOIN pg_attribute child_att ON child_att.attrelid = con.conrelid
      AND child_att.attnum = cols.child_attnum
    JOIN pg_attribute parent_att ON parent_att.attrelid = con.confrelid
      AND parent_att.attnum = cols.parent_attnum
    WHERE con.contype = 'f'
      AND child_ns.nspname = 'public'
      AND parent_ns.nspname = 'public'
      AND child.relkind IN ('r', 'p')
      AND parent.relkind IN ('r', 'p')
      AND EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = con.conrelid
          AND a.attname = 'tenant_id'
          AND a.attnum > 0
          AND NOT a.attisdropped
      )
      AND EXISTS (
        SELECT 1 FROM pg_attribute a
        WHERE a.attrelid = con.confrelid
          AND a.attname = 'tenant_id'
          AND a.attnum > 0
          AND NOT a.attisdropped
      )
    GROUP BY con.oid, con.conname, child_ns.nspname, child.relname,
             parent_ns.nspname, parent.relname
    HAVING NOT bool_or(child_att.attname = 'tenant_id'
                       AND parent_att.attname = 'tenant_id')
    ORDER BY child.relname, con.conname
  LOOP
    EXECUTE format(
      'SELECT count(*) FROM %I.%I AS c JOIN %I.%I AS p ON %s
       WHERE c.tenant_id IS DISTINCT FROM p.tenant_id',
      fk.child_schema, fk.child_table, fk.parent_schema, fk.parent_table,
      fk.join_predicate
    ) INTO mismatches;
    checked := checked + 1;
    IF mismatches > 0 THEN
      affected := affected + 1;
      total_mismatches := total_mismatches + mismatches;
      RAISE WARNING 'CROSS-TENANT FK: %.% -> %.% (%): % linked row(s)',
        fk.child_schema, fk.child_table, fk.parent_schema, fk.parent_table,
        fk.constraint_name, mismatches;
    END IF;
  END LOOP;

  RAISE NOTICE 'FK relationships audited: %', checked;
  RAISE NOTICE 'FK relationships with mismatches: %', affected;
  RAISE NOTICE 'Total mismatched linked rows (sum across FK constraints): %', total_mismatches;

  IF checked <> 48 THEN
    RAISE WARNING 'Schema drift: 48 relationships were expected from the 2026-10-20 baseline, found %', checked;
  END IF;

  IF affected <> 0 THEN
    RAISE EXCEPTION 'FAIL: detected cross-tenant foreign key relationships; investigate before adding composite FKs';
  END IF;
  RAISE NOTICE 'PASS: no existing cross-tenant links found among the % audited FK relationships', checked;
END
$tenant_fk_audit$;
