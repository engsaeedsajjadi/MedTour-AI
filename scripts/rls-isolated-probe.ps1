# Offline RLS feasibility probe: synthetic rows ONLY. Does not read or change MedTour databases.
# Requires Docker Desktop and PowerShell.
$ErrorActionPreference = 'Stop'
$containerName = 'medtour-rls-poc-' + (Get-Date -Format 'yyyyMMddHHmmss')
$temporaryPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$started = $false
try {
    docker run -d --rm --network none --name $containerName -e "POSTGRES_PASSWORD=$temporaryPassword" postgres:17-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated PostgreSQL container.' }
    $started = $true

    $ready = $false
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        docker exec $containerName pg_isready -U postgres -h /var/run/postgresql 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Temporary PostgreSQL did not become ready.' }

    $sql = @'
CREATE ROLE medtour_rls_probe NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE TABLE public.synthetic_patients (
    id text PRIMARY KEY,
    tenant_id text NOT NULL,
    name text NOT NULL
);
INSERT INTO public.synthetic_patients (id,tenant_id,name) VALUES
 ('patient-a','tenant-a','Synthetic A'),
 ('patient-b','tenant-b','Synthetic B');
GRANT USAGE ON SCHEMA public TO medtour_rls_probe;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.synthetic_patients TO medtour_rls_probe;
ALTER TABLE public.synthetic_patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.synthetic_patients FORCE ROW LEVEL SECURITY;
CREATE POLICY synthetic_patients_tenant_scope ON public.synthetic_patients
TO medtour_rls_probe
USING (tenant_id = NULLIF(current_setting('medtour.tenant_id',true),''))
WITH CHECK (tenant_id = NULLIF(current_setting('medtour.tenant_id',true),''));

SET ROLE medtour_rls_probe;
DO $$
BEGIN
 IF (SELECT count(*) FROM public.synthetic_patients) <> 0 THEN
   RAISE EXCEPTION 'Without tenant context, rows were visible';
 END IF;
 RAISE NOTICE 'PASS: no tenant context -> no rows';
END $$;

BEGIN;
SELECT set_config('medtour.tenant_id','tenant-a',true);
DO $$
BEGIN
 IF (SELECT count(*) FROM public.synthetic_patients) <> 1 OR
    (SELECT id FROM public.synthetic_patients LIMIT 1) <> 'patient-a' THEN
   RAISE EXCEPTION 'Tenant A could access another tenant';
 END IF;
 RAISE NOTICE 'PASS: tenant A sees only its own row';
END $$;
DO $$
BEGIN
 BEGIN
  INSERT INTO public.synthetic_patients(id,tenant_id,name)
   VALUES ('foreign-insert','tenant-b','Forbidden');
  RAISE EXCEPTION 'Foreign-tenant insert unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: foreign-tenant INSERT blocked';
 END;
 BEGIN
  UPDATE public.synthetic_patients SET tenant_id='tenant-b' WHERE id='patient-a';
  RAISE EXCEPTION 'Foreign-tenant UPDATE unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'PASS: foreign-tenant UPDATE blocked';
 END;
END $$;
COMMIT;

DO $$
BEGIN
 IF (SELECT count(*) FROM public.synthetic_patients) <> 0 THEN
  RAISE EXCEPTION 'Tenant context leaked after commit';
 END IF;
 RAISE NOTICE 'PASS: tenant context cleared after commit';
END $$;

BEGIN;
SELECT set_config('medtour.tenant_id','tenant-b',true);
DO $$
BEGIN
 IF (SELECT count(*) FROM public.synthetic_patients) <> 1 OR
    (SELECT id FROM public.synthetic_patients LIMIT 1) <> 'patient-b' THEN
  RAISE EXCEPTION 'Tenant B could access another tenant';
 END IF;
 RAISE NOTICE 'PASS: tenant B sees only its own row';
END $$;
COMMIT;
RESET ROLE;
'@
    $sql | docker exec -i $containerName psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres
    if ($LASTEXITCODE -ne 0) { throw 'RLS proof failed.' }
    Write-Host 'PASS: ISOLATED RLS PROOF COMPLETED' -ForegroundColor Green
}
finally {
    if ($started) { docker rm -f $containerName 2>$null | Out-Null }
}
