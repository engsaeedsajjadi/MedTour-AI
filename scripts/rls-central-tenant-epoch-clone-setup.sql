-- Stage 19.23: shared epoch control plane for synthetic PostgreSQL clone.
-- NOT a live migration; execute only as postgres in medtour_principal_clone.
\set ON_ERROR_STOP on
BEGIN;
DO $guard$
BEGIN
  IF current_database() <> 'medtour_principal_clone' OR session_user <> 'postgres' THEN
    RAISE EXCEPTION 'DENIED: clone-only central tenant epoch setup';
  END IF;
END $guard$;

CREATE SCHEMA medtour_control AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA medtour_control FROM PUBLIC;
CREATE TABLE medtour_control.tenant_epochs (
  tenant_id varchar(36) PRIMARY KEY,
  generation bigint NOT NULL CHECK (generation > 0),
  enabled boolean NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON medtour_control.tenant_epochs FROM PUBLIC;
INSERT INTO medtour_control.tenant_epochs (tenant_id,generation,enabled)
VALUES ('__TENANT_A__',1,true),('__TENANT_B__',1,true);

CREATE FUNCTION medtour_control.prevent_rollback() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
 IF NEW.tenant_id <> OLD.tenant_id OR NEW.generation <= OLD.generation THEN
   RAISE EXCEPTION 'DENIED: tenant epoch must advance and tenant ID cannot change';
 END IF;
 NEW.updated_at = now();
 RETURN NEW;
END $fn$;
CREATE TRIGGER tenant_epoch_monotonic
BEFORE UPDATE ON medtour_control.tenant_epochs
FOR EACH ROW EXECUTE FUNCTION medtour_control.prevent_rollback();

CREATE ROLE mt_control_reader LOGIN PASSWORD '__CONTROL_READ_PASS__'
 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE ROLE mt_control_writer LOGIN PASSWORD '__CONTROL_WRITE_PASS__'
 NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
GRANT CONNECT ON DATABASE medtour_principal_clone TO mt_control_reader,mt_control_writer;
GRANT USAGE ON SCHEMA medtour_control TO mt_control_reader,mt_control_writer;
GRANT SELECT ON medtour_control.tenant_epochs TO mt_control_reader,mt_control_writer;
GRANT UPDATE (generation,enabled) ON medtour_control.tenant_epochs TO mt_control_writer;

DO $check$
BEGIN
 IF has_table_privilege('mt_control_reader','public.patients','SELECT')
 OR has_table_privilege('mt_control_reader','public.tenants','SELECT')
 OR has_table_privilege('mt_control_reader','medtour_control.tenant_epochs','UPDATE')
 OR has_table_privilege('mt_control_writer','public.patients','SELECT')
 OR has_table_privilege('mt_control_writer','public.tenants','SELECT')
 OR has_schema_privilege('mt_control_reader','medtour_control','CREATE')
 OR has_schema_privilege('mt_control_writer','medtour_control','CREATE')
 OR pg_has_role('mt_control_reader','mt_clone_a','MEMBER')
 OR pg_has_role('mt_control_writer','mt_clone_b','MEMBER')
 THEN RAISE EXCEPTION 'Control role has unexpected PHI or mutation privilege'; END IF;
END $check$;
COMMIT;
\echo PASS: STAGE 19.23 READ-ONLY CENTRAL TENANT EPOCH CONTROL PLANE READY
