-- MedTour AI: synthetic test of composite tenant-aware foreign keys.
-- MUST ONLY run against a disposable restored clone (NOT the live DB).
-- All added constraints and synthetic records are in the disposable clone.
\set ON_ERROR_STOP on
\pset pager off
BEGIN;

-- Defense against accidental execution on the main database.
DO $clone_only$
BEGIN
 IF current_database() <> 'medtour_fk_clone' OR current_user <> 'postgres' THEN
  RAISE EXCEPTION 'Refusing to run: must use the disposable medtour_fk_clone database as postgres';
 END IF;
END $clone_only$;

CREATE TEMP TABLE mt_fk_targets ON COMMIT DROP AS
SELECT
    con.conname AS old_fk,
    child.relname AS child_table,
    parent.relname AS parent_table,
    cattr.attname AS child_ref_column,
    pattr.attname AS parent_ref_column
FROM pg_constraint con
JOIN pg_class child ON child.oid=con.conrelid
JOIN pg_namespace cn ON cn.oid=child.relnamespace
JOIN pg_class parent ON parent.oid=con.confrelid
JOIN pg_namespace pn ON pn.oid=parent.relnamespace
JOIN pg_attribute cattr ON cattr.attrelid=con.conrelid AND cattr.attnum=con.conkey[1]
JOIN pg_attribute pattr ON pattr.attrelid=con.confrelid AND pattr.attnum=con.confkey[1]
WHERE con.contype='f'
 AND cn.nspname='public' AND pn.nspname='public'
 AND array_length(con.conkey,1)=1 AND array_length(con.confkey,1)=1
 AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=con.conrelid
             AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped)
 AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=con.confrelid
             AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped);

DO $check_targets$
DECLARE expected_count int; all_pairs int;
BEGIN
 SELECT count(*) INTO expected_count FROM mt_fk_targets;
 SELECT count(*) INTO all_pairs FROM pg_constraint con
 JOIN pg_namespace n ON n.oid=con.connamespace
 WHERE con.contype='f' AND n.nspname='public'
 AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=con.conrelid
             AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped)
 AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=con.confrelid
             AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped);
 IF expected_count<>48 OR all_pairs<>expected_count THEN
  RAISE EXCEPTION 'Unexpected FK layout: 48 single-column tenant-to-tenant links required; found % of %',
    expected_count,all_pairs;
 END IF;
 IF EXISTS (SELECT 1 FROM mt_fk_targets WHERE parent_ref_column<>'id') THEN
  RAISE EXCEPTION 'Unexpected referenced primary key; manual review required';
 END IF;
 RAISE NOTICE 'PASS: 48 existing tenant-to-tenant FKs identified on restored schema';
END $check_targets$;

-- PostgreSQL requires a unique key for the two referenced columns.
-- These supporting unique constraints are intentionally created only in the clone.
DO $add_unique$
DECLARE r record;
BEGIN
 FOR r IN SELECT DISTINCT parent_table FROM mt_fk_targets ORDER BY parent_table LOOP
  EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I UNIQUE (tenant_id,id)',
    r.parent_table,'mt_tenant_uq_'||r.parent_table);
 END LOOP;
 RAISE NOTICE 'PASS: composite (tenant_id,id) target keys created on clone';
END $add_unique$;

-- Add strict tenant-aware FKs alongside original FKs to measure compatibility.
-- Not a production migration: original ON DELETE/ON UPDATE behavior must be reviewed
-- and a final replacement migration must preserve it.
DO $add_fk$
DECLARE r record;
BEGIN
 FOR r IN SELECT * FROM mt_fk_targets ORDER BY child_table,child_ref_column LOOP
   EXECUTE format(
    'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (tenant_id,%I) REFERENCES public.%I (tenant_id,%I) NOT VALID',
    r.child_table, 'mt_fk_'||r.child_table||'_'||r.child_ref_column,
    r.child_ref_column, r.parent_table, r.parent_ref_column
   );
 END LOOP;
 RAISE NOTICE 'PASS: 48 composite tenant-aware FKs added to clone';
END $add_fk$;

-- Validating all constraints checks all existing rows on the restored backup.
DO $validate_fk$
DECLARE r record;
BEGIN
 FOR r IN SELECT * FROM mt_fk_targets ORDER BY child_table,child_ref_column LOOP
   EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I',
     r.child_table, 'mt_fk_'||r.child_table||'_'||r.child_ref_column);
 END LOOP;
 IF (
   SELECT count(*) FROM pg_constraint con
   JOIN pg_class cl ON cl.oid=con.conrelid
   JOIN pg_namespace ns ON ns.oid=cl.relnamespace
   WHERE ns.nspname='public' AND con.contype='f'
     AND con.conname LIKE 'mt_fk_%' AND con.convalidated
 )<>48 THEN RAISE EXCEPTION 'Not all 48 tenant-aware FKs are validated'; END IF;
 RAISE NOTICE 'PASS: all 48 new composite FKs validated against restored data';
END $validate_fk$;

-- Use synthetic IDs, unrelated to any existing patient records, for negative tests.
INSERT INTO public.tenants(id,slug,name,created_at) VALUES
  ('__TENANT_A__','mt-fk-clone-a','Synthetic FK Tenant A',now()),
  ('__TENANT_B__','mt-fk-clone-b','Synthetic FK Tenant B',now());
INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at) VALUES
  ('__PATIENT_A__','__TENANT_A__','Synthetic FK Patient A','','en','',now()),
  ('__PATIENT_B__','__TENANT_B__','Synthetic FK Patient B','','en','',now());
INSERT INTO public.cases(id,tenant_id,patient_id,complaint,specialty,status,created_at)
VALUES ('__CASE_A__','__TENANT_A__','__PATIENT_A__','Synthetic request','','new',now());

DO $exercise_fk$
BEGIN
 IF (SELECT count(*) FROM public.cases WHERE id='__CASE_A__')<>1 THEN
  RAISE EXCEPTION 'Valid in-tenant case insert failed';
 END IF;
 RAISE NOTICE 'PASS: valid same-tenant patient/case relationship accepted';
 BEGIN
  UPDATE public.cases SET patient_id='__PATIENT_B__' WHERE id='__CASE_A__';
  RAISE EXCEPTION 'ERROR: cross-tenant UPDATE was accepted';
 EXCEPTION WHEN foreign_key_violation THEN
  RAISE NOTICE 'PASS: cross-tenant patient_id UPDATE rejected by composite FK';
 END;
 BEGIN
  INSERT INTO public.cases(id,tenant_id,patient_id,complaint,specialty,status,created_at)
    VALUES ('__CASE_BAD__','__TENANT_A__','__PATIENT_B__','Invalid','','new',now());
  RAISE EXCEPTION 'ERROR: cross-tenant INSERT was accepted';
 EXCEPTION WHEN foreign_key_violation THEN
  RAISE NOTICE 'PASS: cross-tenant patient_id INSERT rejected by composite FK';
 END;
END $exercise_fk$;

COMMIT;
\echo PASS: ISOLATED COMPOSITE FK CLONE TEST COMPLETED
