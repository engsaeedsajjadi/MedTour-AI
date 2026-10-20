-- TEST ONLY: this file MUST run against disposable medtour_role_clone.
-- SQL contains only synthetic records. Never execute on the live database.
\set ON_ERROR_STOP on
\pset pager off
BEGIN;

DO $guard$
BEGIN
 IF current_database()<>'medtour_role_clone' OR current_user<>'postgres' THEN
   RAISE EXCEPTION 'Refusing changes outside disposable medtour_role_clone/postgres';
 END IF;
END $guard$;

CREATE ROLE medtour_app LOGIN PASSWORD '__APP_PASSWORD__'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

GRANT CONNECT ON DATABASE medtour_role_clone TO medtour_app;
GRANT USAGE ON SCHEMA public TO medtour_app;

INSERT INTO public.tenants (id,slug,name,created_at)
VALUES ('__TENANT_A__','isolated-role-a','Synthetic A',now()),
       ('__TENANT_B__','isolated-role-b','Synthetic B',now());
INSERT INTO public.patients (id,tenant_id,full_name,country,language,contact,created_at)
VALUES ('__PATIENT_A__','__TENANT_A__','Synthetic A','','en','',now()),
       ('__PATIENT_B__','__TENANT_B__','Synthetic B','','en','',now());

DO $setup$
DECLARE r record; table_count integer := 0;
BEGIN
 FOR r IN SELECT cl.relname FROM pg_class cl
  JOIN pg_namespace ns ON ns.oid=cl.relnamespace
  JOIN pg_attribute a ON a.attrelid=cl.oid
  WHERE ns.nspname='public' AND cl.relkind IN ('r','p')
    AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
  ORDER BY cl.relname
 LOOP
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO medtour_app',r.relname);
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',r.relname);
  EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',r.relname);
  EXECUTE format(
   'CREATE POLICY medtour_clone_app_tenant ON public.%I TO medtour_app FOR ALL USING (tenant_id = NULLIF(current_setting(''medtour.tenant_id'',true),'''')) WITH CHECK (tenant_id = NULLIF(current_setting(''medtour.tenant_id'',true),''''))',r.relname);
  table_count := table_count + 1;
 END LOOP;
 IF table_count <> 37 THEN RAISE EXCEPTION 'Schema drift: expected 37 tenant tables, found %',table_count; END IF;
 RAISE NOTICE 'PASS: RLS policies + DML grants applied to all 37 operational tables in clone';
END $setup$;

DO $verify$
DECLARE owner_count integer;
BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='medtour_app'
  AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication OR rolinherit)) THEN
  RAISE EXCEPTION 'App role has elevated attributes';
 END IF;
 SELECT count(*) INTO owner_count FROM pg_class c
 JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
 AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname='medtour_app');
 IF owner_count<>0 THEN RAISE EXCEPTION 'App role owns % tables',owner_count; END IF;
 IF has_table_privilege('medtour_app','public.tenants','SELECT')
  OR has_table_privilege('medtour_app','public.alembic_version','SELECT')
  OR has_table_privilege('medtour_app','public.patients','TRUNCATE')
  OR has_schema_privilege('medtour_app','public','CREATE')
  OR pg_has_role('medtour_app','postgres','MEMBER') THEN
  RAISE EXCEPTION 'App role has an unintended privilege';
 END IF;
 RAISE NOTICE 'PASS: role cannot bypass RLS, own tables, create schema objects, switch to postgres, or read administrative tables';
END $verify$;
COMMIT;
\echo PASS: CLONE-ONLY ROLE PROVISIONING COMPLETE
