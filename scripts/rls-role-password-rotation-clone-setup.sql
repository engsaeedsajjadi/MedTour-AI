-- Stage 19.24 — clone-only privileged database password rotation boundary.
-- This script MUST NEVER be applied to a production database.
\set ON_ERROR_STOP on
BEGIN;
DO $safe$
BEGIN
 IF current_database() <> 'medtour_principal_clone' OR session_user <> 'postgres' THEN
  RAISE EXCEPTION 'DENIED: rotation setup only inside medtour_principal_clone as postgres';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mt_clone_a') THEN
  RAISE EXCEPTION 'DENIED: missing synthetic principal';
 END IF;
END $safe$;

CREATE ROLE mt_rotation_operator LOGIN PASSWORD '__ROTATE_OPERATOR_PASS__'
 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
GRANT CONNECT ON DATABASE medtour_principal_clone TO mt_rotation_operator;
GRANT USAGE ON SCHEMA medtour_control TO mt_rotation_operator;

-- Narrow privilege elevation for exactly one synthetic tenant role:
-- a separate test-only operator cannot alter arbitrary database principals,
-- read patient rows, update tenant epochs or issue general DDL.
CREATE FUNCTION medtour_control.rotate_synthetic_a(
 target_tenant text, expected_generation bigint, new_secret text
) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog, medtour_control
AS $rotate$
DECLARE
  epoch_value bigint;
  currently_enabled boolean;
  connections_killed integer;
BEGIN
 IF session_user <> 'mt_rotation_operator'
    OR current_database() <> 'medtour_principal_clone'
    OR target_tenant <> '__TENANT_A__'
    OR expected_generation < 2
    OR new_secret IS NULL OR length(new_secret)<40 OR length(new_secret)>200
    OR new_secret !~ '^[A-Za-z0-9_-]+$' THEN
  RAISE EXCEPTION 'DENIED: invalid scoped rotation request';
 END IF;

 SELECT generation, enabled INTO epoch_value, currently_enabled
 FROM medtour_control.tenant_epochs
 WHERE tenant_id=target_tenant FOR UPDATE;
 IF epoch_value IS DISTINCT FROM expected_generation
    OR currently_enabled IS DISTINCT FROM false THEN
  RAISE EXCEPTION 'DENIED: tenant must be disabled at exact epoch';
 END IF;

 EXECUTE pg_catalog.format(
   'ALTER ROLE %I LOGIN PASSWORD %L', 'mt_clone_a', new_secret
 );
 SELECT count(*)::integer INTO connections_killed
 FROM pg_catalog.pg_stat_activity
 WHERE datname=current_database() AND usename='mt_clone_a' AND pid<>pg_backend_pid();
 PERFORM pg_catalog.pg_terminate_backend(pid)
 FROM pg_catalog.pg_stat_activity
 WHERE datname=current_database() AND usename='mt_clone_a' AND pid<>pg_backend_pid();

 RETURN connections_killed;
END
$rotate$;

REVOKE ALL ON FUNCTION medtour_control.rotate_synthetic_a(text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION medtour_control.rotate_synthetic_a(text,bigint,text)
 TO mt_rotation_operator;

DO $least$
BEGIN
 IF has_table_privilege('mt_rotation_operator','public.patients','SELECT')
 OR has_table_privilege('mt_rotation_operator','public.tenants','SELECT')
 OR has_table_privilege('mt_rotation_operator','medtour_control.tenant_epochs','UPDATE')
 OR has_table_privilege('mt_rotation_operator','medtour_control.tenant_epochs','SELECT')
 OR has_schema_privilege('mt_rotation_operator','medtour_control','CREATE')
 OR pg_has_role('mt_rotation_operator','mt_clone_a','MEMBER')
 OR pg_has_role('mt_rotation_operator','postgres','MEMBER')
 OR (SELECT rolsuper OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname='mt_rotation_operator')
 THEN RAISE EXCEPTION 'Rotation operator must not have broad DB privileges'; END IF;
END $least$;
COMMIT;
\echo PASS: STAGE 19.24 CLONE-ONLY LIMITED ROTATION OPERATOR READY
