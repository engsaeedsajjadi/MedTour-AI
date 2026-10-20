# Tests 48 tenant-aware FK constraints on a disposable, restored PostgreSQL 17 clone.
# No access to the live MedTour database; uses Docker --network none.
# IMPORTANT: use ONLY a development backup with synthetic non-PHI data.
param([string]$BackupFile = '')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sqlPath = Join-Path $PSScriptRoot 'tenant-composite-fk-clone.sql'
if (!(Test-Path -LiteralPath $sqlPath)) {
    throw "Clone-only SQL not found: $sqlPath"
}

if (!$BackupFile) {
    $folder = Join-Path (Split-Path -Parent $projectRoot) 'MedTour-AI-Backups'
    $recent = Get-ChildItem -LiteralPath $folder -Filter 'medtour-*.dump' -File |
      Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$recent) { throw "No matching synthetic-development backup in $folder" }
    $BackupFile = $recent.FullName
}
$BackupFile = (Resolve-Path -LiteralPath $BackupFile).Path
if ((Get-Item -LiteralPath $BackupFile).Length -eq 0) { throw 'Backup file is empty' }

$name = 'medtour-fk-clone-' + (Get-Date -Format 'yyyyMMddHHmmss') + '-' + $PID
$password = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$started = $false
function CheckDocker([string]$failure) {
    if ($LASTEXITCODE -ne 0) { throw $failure }
}

try {
    Write-Host 'Starting network-isolated PostgreSQL 17 clone (no Compose data touched)...'
    docker run -d --rm --network none --name $name -e "POSTGRES_PASSWORD=$password" postgres:17-alpine | Out-Null
    CheckDocker 'Unable to create temporary Docker container'
    $started = $true

    $ready = $false
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        docker exec $name pg_isready -U postgres -h /var/run/postgresql 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Temporary PostgreSQL server is not ready' }

    docker cp "$BackupFile" ($name + ':/tmp/medtour-synthetic.dump') | Out-Null
    CheckDocker 'Unable to copy development backup into clone'
    docker exec $name pg_restore --list /tmp/medtour-synthetic.dump | Out-Null
    CheckDocker 'Invalid PostgreSQL backup archive'
    docker exec $name createdb -U postgres medtour_fk_clone
    CheckDocker 'Unable to create temporary clone database'
    docker exec $name pg_restore --single-transaction --no-owner --no-acl -U postgres -d medtour_fk_clone /tmp/medtour-synthetic.dump
    CheckDocker 'Restoring the development database into clone failed'
    Write-Host 'PASS: restored development backup into an isolated clone'

    $ids = @{
        '__TENANT_A__'  = [guid]::NewGuid().ToString()
        '__TENANT_B__'  = [guid]::NewGuid().ToString()
        '__PATIENT_A__' = [guid]::NewGuid().ToString()
        '__PATIENT_B__' = [guid]::NewGuid().ToString()
        '__CASE_A__'    = [guid]::NewGuid().ToString()
        '__CASE_BAD__'  = [guid]::NewGuid().ToString()
    }
    $sql = Get-Content -Raw -Encoding UTF8 -LiteralPath $sqlPath
    foreach ($key in $ids.Keys) {
        $sql = $sql.Replace($key, $ids[$key])
    }

    $sql | docker exec -i $name psql -X -v ON_ERROR_STOP=1 -U postgres -d medtour_fk_clone
    CheckDocker 'Tenant-aware FK clone test failed'
    Write-Host 'PASS: COMPOSITE FK AUDIT VERIFIED ON ISOLATED RESTORED DATABASE' -ForegroundColor Green
}
finally {
    if ($started) {
        docker rm -f $name 2>$null | Out-Null
    }
}
