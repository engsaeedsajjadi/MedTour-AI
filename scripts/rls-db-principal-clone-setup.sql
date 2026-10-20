-- Stage 19.13: PostgreSQL authenticated-database-principal proof.
-- NOT a migration. Runs only inside disposable medtour_principal_clone.
\set ON_ERROR_STOP on
\pset pager off
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'medtour_principal_clone' OR current_user <> 'postgres' THEN
  RAISE EXCEPTION 'DENIED: principal POC only runs in isolated medtour_principal_clone as postgres';
 END IF;
END $guard$;

-- Two non-superuser, non-owner LOGIN principals, with NO memberships.
CREATE ROLE mt_clone_a LOGIN PASSWORD '__PASS_A__'
 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE ROLE mt_clone_b LOGIN PASSWORD '__PASS_B__'
 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

REVOKE CONNECT ON DATABASE medtour_principal_clone FROM PUBLIC;
GRANT CONNECT ON DATABASE medtour_principal_clone TO mt_clone_a, mt_clone_b;
GRANT USAGE ON SCHEMA public TO mt_clone_a, mt_clone_b;

-- Mapping is stored in a private schema, never writable/readable by runtime roles.
CREATE SCHEMA medtour_principal_private AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA medtour_principal_private FROM PUBLIC;
CREATE TABLE medtour_principal_private.role_tenant_mapping
 (database_role name PRIMARY KEY, tenant_id varchar(36) NOT NULL UNIQUE);
REVOKE ALL ON TABLE medtour_principal_private.role_tenant_mapping FROM PUBLIC;

INSERT INTO public.tenants(id,slug,name,created_at)
VALUES ('__TENANT_A__','principal-poc-a','Synthetic Principal A',now()),
       ('__TENANT_B__','principal-poc-b','Synthetic Principal B',now());
INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at)
VALUES ('__PATIENT_A__','__TENANT_A__','Synthetic A','','en','',now()),
       ('__PATIENT_B__','__TENANT_B__','Synthetic B','','en','',now());
INSERT INTO medtour_principal_private.role_tenant_mapping(database_role,tenant_id)
VALUES ('mt_clone_a','__TENANT_A__'),('mt_clone_b','__TENANT_B__');

-- SECURITY DEFINER switches current_user to function owner, therefore use
-- session_user (the authenticated login principal) as the lookup identity.
-- Ordinary SQL cannot change session_user to another login role.
CREATE FUNCTION medtour_principal_private.tenant_for_login()
RETURNS varchar(36)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, medtour_principal_private
AS $fn$
 SELECT m.tenant_id
 FROM medtour_principal_private.role_tenant_mapping AS m
 WHERE m.database_role = session_user
$fn$;
REVOKE ALL ON FUNCTION medtour_principal_private.tenant_for_login() FROM PUBLIC;
GRANT USAGE ON SCHEMA medtour_principal_private TO mt_clone_a, mt_clone_b;
GRANT EXECUTE ON FUNCTION medtour_principal_private.tenant_for_login()
 TO mt_clone_a, mt_clone_b;

-- Explicit table privileges plus policy; RLS does not grant SELECT by itself.
DO $rls$
DECLARE r record; secured integer := 0;
BEGIN
 FOR r IN
   SELECT c.relname FROM pg_class c
   JOIN pg_namespace ns ON ns.oid=c.relnamespace
   JOIN pg_attribute a ON a.attrelid=c.oid
   WHERE ns.nspname='public' AND c.relkind IN ('r','p')
    AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
   ORDER BY c.relname
 LOOP
   EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO mt_clone_a, mt_clone_b',r.relname);
   EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',r.relname);
   EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',r.relname);
   EXECUTE format(
     'CREATE POLICY mt_login_isolation ON public.%I FOR ALL TO mt_clone_a, mt_clone_b USING (tenant_id = medtour_principal_private.tenant_for_login()) WITH CHECK (tenant_id = medtour_principal_private.tenant_for_login())',
     r.relname);
   secured := secured + 1;
 END LOOP;
 IF secured <> 37 THEN
   RAISE EXCEPTION 'Expected 37 operational tenant tables; got %', secured;
 END IF;
 RAISE NOTICE 'PASS: 37 tenant tables secured by database-login-principal policies on clone';
END $rls$;

DO $grants$
DECLARE count_owned int;
BEGIN
 SELECT count(*) INTO count_owned FROM pg_class c
 JOIN pg_namespace ns ON ns.oid=c.relnamespace
 WHERE ns.nspname='public' AND c.relkind IN ('r','p')
 AND c.relowner IN ((SELECT oid FROM pg_roles WHERE rolname='mt_clone_a'),
                    (SELECT oid FROM pg_roles WHERE rolname='mt_clone_b'));
 IF count_owned <> 0 THEN RAISE EXCEPTION 'App role owns operational table(s)'; END IF;
 IF has_table_privilege('mt_clone_a','public.tenants','SELECT')
 OR has_table_privilege('mt_clone_b','public.alembic_version','SELECT')
 OR has_table_privilege('mt_clone_a','public.patients','TRUNCATE')
 OR has_table_privilege('mt_clone_b','public.patients','TRUNCATE')
 OR has_table_privilege('mt_clone_a','medtour_principal_private.role_tenant_mapping','SELECT')
 OR has_table_privilege('mt_clone_b','medtour_principal_private.role_tenant_mapping','SELECT')
 OR has_schema_privilege('mt_clone_a','medtour_principal_private','CREATE')
 OR pg_has_role('mt_clone_a','mt_clone_b','MEMBER')
 OR pg_has_role('mt_clone_b','mt_clone_a','MEMBER')
 THEN RAISE EXCEPTION 'Unintended privilege found'; END IF;
 RAISE NOTICE 'PASS: both roles have no privileged membership, mapping-table SELECT, or TRUNCATE rights';
END $grants$;
COMMIT;
\echo PASS: DATABASE-LOGIN-PRINCIPAL CLONE SETUP COMPLETED
