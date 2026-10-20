-- Validates one authenticated tenant-scoped database principal on the clone.
-- Parameter placeholders are replaced by the PowerShell driver.
\set ON_ERROR_STOP on
\pset pager off
DO $identity$
BEGIN
 IF current_database()<>'medtour_principal_clone'
 OR session_user<>'__EXPECTED_ROLE__'
 OR current_user<>'__EXPECTED_ROLE__'
 THEN RAISE EXCEPTION 'Unexpected database principal or database target'; END IF;
 IF (SELECT rolsuper OR rolbypassrls OR rolcreaterole FROM pg_roles WHERE rolname=current_user)
 THEN RAISE EXCEPTION 'Unexpected elevated runtime role'; END IF;
 IF medtour_principal_private.tenant_for_login()<>'__OWN_TENANT__'
 THEN RAISE EXCEPTION 'Authenticated principal mapped to wrong tenant'; END IF;
 RAISE NOTICE 'PASS: authenticated role % resolves tenant from protected mapping',session_user;
END $identity$;

DO $reads$
DECLARE r record; n bigint; total integer := 0;
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__OWN_PATIENT__')<>1 OR
 (SELECT count(*) FROM public.patients WHERE id='__OTHER_PATIENT__')<>0
 THEN RAISE EXCEPTION 'Principal sees foreign patient'; END IF;
 FOR r IN SELECT c.relname FROM pg_class c
 JOIN pg_namespace ns ON ns.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE ns.nspname='public' AND c.relkind IN ('r','p')
 AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
 LOOP
  EXECUTE format('SELECT count(*) FROM public.%I WHERE tenant_id <> %L',
        r.relname,'__OWN_TENANT__') INTO n;
  IF n<>0 THEN RAISE EXCEPTION 'Foreign rows visible in table %',r.relname; END IF;
  total:=total+1;
 END LOOP;
 IF total<>37 THEN RAISE EXCEPTION 'Schema drift: % tables',total; END IF;
 RAISE NOTICE 'PASS: own tenant allowed, foreign rows invisible across 37 operational tables';
END $reads$;

-- The custom variable may be changed by ordinary SQL, but policies must ignore it.
SELECT set_config('medtour.tenant_id','__OTHER_TENANT__',false) AS forged_context;
DO $guc$
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__OWN_PATIENT__')<>1 OR
 (SELECT count(*) FROM public.patients WHERE id='__OTHER_PATIENT__')<>0 THEN
 RAISE EXCEPTION 'Forged GUC changed effective tenant'; END IF;
 RAISE NOTICE 'PASS: forging medtour.tenant_id cannot change the RLS identity';
END $guc$;

DO $role_escalation$
BEGIN
 BEGIN
  EXECUTE 'SET ROLE __OTHER_ROLE__';
  RAISE EXCEPTION 'Cross-tenant SET ROLE unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: changing DB role to other tenant denied';
 END;
 BEGIN
  EXECUTE 'SET SESSION AUTHORIZATION __OTHER_ROLE__';
  RAISE EXCEPTION 'Cross-tenant session authorization unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: changing session authorization to other tenant denied';
 END;
 IF session_user <> '__EXPECTED_ROLE__' OR current_user <> '__EXPECTED_ROLE__' THEN
  RAISE EXCEPTION 'Principal unexpectedly changed';
 END IF;
END $role_escalation$;

DO $restrictions$
DECLARE n bigint;
BEGIN
 BEGIN
  EXECUTE 'SELECT count(*) FROM public.tenants' INTO n;
  RAISE EXCEPTION 'Tenant registry readable by app role';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: privileged tenant registry SELECT denied';
 END;
 BEGIN
  EXECUTE 'SELECT count(*) FROM medtour_principal_private.role_tenant_mapping' INTO n;
  RAISE EXCEPTION 'Protected tenant mapping readable by app role';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: protected principal-to-tenant mapping SELECT denied';
 END;
 BEGIN
  EXECUTE 'UPDATE medtour_principal_private.role_tenant_mapping SET tenant_id = ''__OTHER_TENANT__'' WHERE database_role = session_user';
  RAISE EXCEPTION 'Protected role mapping writable by app role';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: protected principal-to-tenant mapping UPDATE denied';
 END;
 BEGIN
  INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at)
   VALUES ('__BLOCKED_PATIENT__','__OTHER_TENANT__','Blocked','','en','',now());
  RAISE EXCEPTION 'Cross-tenant patient insertion succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: cross-tenant INSERT denied by authenticated-principal RLS';
 END;
 BEGIN
  UPDATE public.patients SET tenant_id='__OTHER_TENANT__' WHERE id='__OWN_PATIENT__';
  RAISE EXCEPTION 'Cross-tenant patient update succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: cross-tenant UPDATE denied by authenticated-principal RLS';
 END;
END $restrictions$;

\echo PASS: ONE DIRECT DATABASE TENANT PRINCIPAL VERIFIED
