# Runs against a disposable restored PostgreSQL 17 clone, NEVER the live database.
# Use only with an approved, synthetic-development backup.
param([string]$BackupFile = "")
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (!$BackupFile) {
  $folder = Join-Path (Split-Path -Parent $project) 'MedTour-AI-Backups'
  $latest = Get-ChildItem -LiteralPath $folder -Filter 'medtour-*.dump' -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (!$latest) { throw "No backup found in $folder" }
  $BackupFile = $latest.FullName
}
$BackupFile = (Resolve-Path -LiteralPath $BackupFile).Path
if ((Get-Item -LiteralPath $BackupFile).Length -eq 0) { throw 'Empty backup' }
$name = 'medtour-rls-restored-' + (Get-Date -Format 'yyyyMMddHHmmss') + '-' + $PID
$password = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$started = $false
function Verify([string]$message) { if ($LASTEXITCODE -ne 0) { throw $message } }
try {
  docker run -d --rm --network none --name $name -e "POSTGRES_PASSWORD=$password" postgres:17-alpine | Out-Null
  Verify 'Failed to start isolated Postgres'
  $started = $true
  $ready = $false
  for ($i=1;$i -le 40;$i++) {
    docker exec $name pg_isready -U postgres -h /var/run/postgresql 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (!$ready) { throw 'PostgreSQL not ready' }
  docker cp "$BackupFile" ($name + ':/tmp/medtour.dump') | Out-Null
  Verify 'Copy failed'
  docker exec $name createdb -U postgres medtour_rls_clone
  Verify 'Cannot create clone database'
  docker exec $name pg_restore --single-transaction --no-owner --no-acl -U postgres -d medtour_rls_clone /tmp/medtour.dump
  Verify 'Restore failed'
  Write-Host 'PASS: backup restored in a network-isolated PostgreSQL clone'

  $a = [guid]::NewGuid().ToString()
  $b = [guid]::NewGuid().ToString()
  $pa = [guid]::NewGuid().ToString()
  $pb = [guid]::NewGuid().ToString()
  $foreign = [guid]::NewGuid().ToString()
  $sql = @'
CREATE ROLE medtour_rls_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO medtour_rls_app;
INSERT INTO public.tenants (id,slug,name,created_at)
VALUES ('__A__','rls-probe-a','Synthetic A',now()),('__B__','rls-probe-b','Synthetic B',now());
INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at)
VALUES
 ('__PA__','__A__','Synthetic Patient A','','en','',now()),
 ('__PB__','__B__','Synthetic Patient B','','en','',now());

DO $setup$
DECLARE r record;
BEGIN
 FOR r IN
  SELECT c.relname FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid
  WHERE n.nspname='public' AND c.relkind IN ('r','p')
    AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
 LOOP
   EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO medtour_rls_app',r.relname);
   EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',r.relname);
   EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',r.relname);
   EXECUTE format(
    'CREATE POLICY medtour_rls_trial ON public.%I FOR ALL TO medtour_rls_app USING (tenant_id = NULLIF(current_setting(''medtour.tenant_id'',true),'''')) WITH CHECK (tenant_id = NULLIF(current_setting(''medtour.tenant_id'',true),''''))',r.relname);
 END LOOP;
END $setup$;

DO $verify$
DECLARE t int; s int;
BEGIN
 SELECT count(*) INTO t FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid
  WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped;
 SELECT count(*) INTO s FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid
  WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
    AND c.relrowsecurity AND c.relforcerowsecurity
    AND EXISTS(SELECT 1 FROM pg_policy p WHERE p.polrelid=c.oid AND p.polname='medtour_rls_trial');
 IF t<>37 OR s<>37 THEN RAISE EXCEPTION 'Expected 37 protected tenant tables; got %, %',t,s; END IF;
 IF (SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname='medtour_rls_app') THEN
   RAISE EXCEPTION 'Runtime role must not bypass RLS';
 END IF;
 IF has_table_privilege('medtour_rls_app','public.tenants','SELECT') OR
    has_table_privilege('medtour_rls_app','public.alembic_version','SELECT') OR
    has_table_privilege('medtour_rls_app','public.patients','TRUNCATE') THEN
   RAISE EXCEPTION 'Runtime role has unauthorized privileges';
 END IF;
 RAISE NOTICE 'PASS: 37 tenant-scoped tables have ENABLE+FORCE RLS and policies';
 RAISE NOTICE 'PASS: non-superuser app role lacks admin-table and TRUNCATE rights';
END $verify$;

SET ROLE medtour_rls_app;
DO $missing$
DECLARE r record; n bigint;
BEGIN
 FOR r IN SELECT c.relname FROM pg_class c
   JOIN pg_namespace ns ON ns.oid=c.relnamespace
   JOIN pg_attribute a ON a.attrelid=c.oid
   WHERE ns.nspname='public' AND c.relkind IN ('r','p')
    AND a.attname='tenant_id' AND a.attnum>0 AND NOT a.attisdropped
 LOOP
   EXECUTE format('SELECT count(*) FROM public.%I',r.relname) INTO n;
   IF n<>0 THEN RAISE EXCEPTION 'Unscoped rows visible: %',r.relname; END IF;
 END LOOP;
 RAISE NOTICE 'PASS: no tenant context means zero visible rows in all 37 tables';
END $missing$;

BEGIN;
SELECT set_config('medtour.tenant_id','__A__',true);
DO $read_a$
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__PA__')<>1 OR
    (SELECT count(*) FROM public.patients WHERE id='__PB__')<>0 THEN
  RAISE EXCEPTION 'Tenant A can see foreign data';
 END IF;
 RAISE NOTICE 'PASS: tenant A can read only its own synthetic patient';
END $read_a$;
DO $deny_write$
BEGIN
 BEGIN
   INSERT INTO public.patients(id,tenant_id,full_name,country,language,contact,created_at)
    VALUES ('__X__','__B__','Forbidden','','en','',now());
   RAISE EXCEPTION 'Cross-tenant INSERT unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
   RAISE NOTICE 'PASS: cross-tenant INSERT rejected';
 END;
 BEGIN
   UPDATE public.patients SET tenant_id='__B__' WHERE id='__PA__';
   RAISE EXCEPTION 'Cross-tenant UPDATE unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
   RAISE NOTICE 'PASS: cross-tenant UPDATE rejected';
 END;
END $deny_write$;
COMMIT;

DO $reset$
BEGIN
 IF (SELECT count(*) FROM public.patients)<>0 THEN RAISE EXCEPTION 'Tenant context leaked across commits'; END IF;
 RAISE NOTICE 'PASS: context cleared after commit';
END $reset$;

BEGIN;
SELECT set_config('medtour.tenant_id','__B__',true);
DO $read_b$
BEGIN
 IF (SELECT count(*) FROM public.patients WHERE id='__PB__')<>1 OR
    (SELECT count(*) FROM public.patients WHERE id='__PA__')<>0 THEN
  RAISE EXCEPTION 'Tenant B can see foreign data';
 END IF;
 RAISE NOTICE 'PASS: tenant B can read only its own synthetic patient';
END $read_b$;
COMMIT;
RESET ROLE;
'@
  $sql = $sql.Replace('__A__',$a).Replace('__B__',$b).Replace('__PA__',$pa).Replace('__PB__',$pb).Replace('__X__',$foreign)
  $sql | docker exec -i $name psql -X -q -v ON_ERROR_STOP=1 -U postgres -d medtour_rls_clone
  Verify 'Isolated RLS audit failed'
  Write-Host 'PASS: RESTORED-SCHEMA RLS AUDIT COMPLETED'
}
finally {
  if ($started) { docker rm -f $name 2>$null | Out-Null }
}
