-- Authenticated LOGIN-role proof for MedTour AI restored clone ONLY.
-- This intentionally demonstrates that a client-controlled GUC is spoofable.
\set ON_ERROR_STOP on
\pset pager off

DO $auth_role$
DECLARE role_name text;
BEGIN
 SELECT current_user INTO role_name;
 IF current_database()<>'medtour_role_clone' OR role_name<>'medtour_app' THEN
  RAISE EXCEPTION 'Not connected as medtour_app to disposable role clone';
 END IF;
 IF (SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user) THEN
  RAISE EXCEPTION 'Runtime login has elevated privileges';
 END IF;
 RAISE NOTICE 'PASS: direct database login uses unprivileged medtour_app, not postgres';
END $auth_role$;

DO $deny_privileges$
DECLARE n bigint;
BEGIN
 BEGIN
  EXECUTE 'SELECT count(*) FROM public.tenants' INTO n;
  RAISE EXCEPTION 'App role unexpectedly read tenants';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: app role cannot read tenants directly';
 END;
 BEGIN
  EXECUTE 'SELECT count(*) FROM public.alembic_version' INTO n;
  RAISE EXCEPTION 'App role unexpectedly read migration version';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: app role cannot read migration version';
 END;
 BEGIN
  EXECUTE 'TRUNCATE public.patients';
  RAISE EXCEPTION 'App role unexpectedly truncated patients';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: TRUNCATE denied for app role';
 END;
 BEGIN
  EXECUTE 'CREATE TABLE public.medtour_should_not_create (x int)';
  RAISE EXCEPTION 'App role unexpectedly created public table';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: CREATE TABLE denied for app role';
 END;
END $deny_privileges$;

DO $unscoped$
DECLARE r record; n bigint; total integer := 0;
BEGIN
 FOR r IN SELECT c.relname FROM pg_class c
  JOIN pg_namespace ns ON ns.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid
  WHERE ns.nspname='public' AND c.relkind IN ('r','p')
    AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
 LOOP
  EXECUTE format('SELECT count(*) FROM public.%I',r.relname) INTO n;
  IF n<>0 THEN RAISE EXCEPTION 'Unscoped data visible in %',r.relname; END IF;
  total := total + 1;
 END LOOP;
 IF total<>37 THEN RAISE EXCEPTION 'Expected 37 tables, got %',total; END IF;
 RAISE NOTICE 'PASS: unscoped runtime login sees zero rows from 37 tenant tables';
END $unscoped$;

BEGIN;
SELECT set_config('medtour.tenant_id','__TENANT_A__',true) AS scoped_tenant_a;
DO $scope_a$
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__PATIENT_A__')<>1
    OR (SELECT count(*) FROM public.patients WHERE id='__PATIENT_B__')<>0 THEN
  RAISE EXCEPTION 'Tenant A read boundary failed';
 END IF;
 RAISE NOTICE 'PASS: runtime session scoped to Tenant A reads A, not B';
END $scope_a$;
COMMIT;

DO $clear$
BEGIN
 IF (SELECT count(*) FROM public.patients)<>0 THEN
  RAISE EXCEPTION 'Tenant context persisted after commit';
 END IF;
 RAISE NOTICE 'PASS: tenant scope is not retained after commit';
END $clear$;

BEGIN;
SELECT set_config('medtour.tenant_id','__TENANT_B__',true) AS scoped_tenant_b;
DO $scope_b$
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__PATIENT_B__')<>1
    OR (SELECT count(*) FROM public.patients WHERE id='__PATIENT_A__')<>0 THEN
  RAISE EXCEPTION 'Tenant B read boundary failed';
 END IF;
 RAISE NOTICE 'PASS: runtime session scoped to Tenant B reads B, not A';
END $scope_b$;
COMMIT;

-- SECURITY WARNING, not an enterprise success assertion:
-- A role with arbitrary SQL execution can supply a different tenant GUC.
BEGIN;
SELECT set_config('medtour.tenant_id','__TENANT_A__',true) AS initial_context;
SELECT set_config('medtour.tenant_id','__TENANT_B__',true) AS altered_context;
DO $guc_warning$
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__PATIENT_B__')<>1 THEN
  RAISE EXCEPTION 'Unexpected GUC spoof behavior';
 END IF;
 RAISE WARNING 'P0 SECURITY GAP: runtime SQL can change medtour.tenant_id; this prototype is NOT production-safe against arbitrary SQL execution';
END $guc_warning$;
ROLLBACK;
\echo PASS: ISOLATED APP LOGIN AND LEAST-PRIVILEGE TEST COMPLETED (GUC SPOOFING RISK REMAINS)
