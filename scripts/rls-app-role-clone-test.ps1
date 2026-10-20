# Stage 19.12: Test a real least-privilege LOGIN role on a disposable restored clone.
# Requires Docker Desktop. Never connects to the live Compose database or volumes.
# Backup MUST contain only synthetic development records (no actual patient information).
param([string]$BackupFile = '')

$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptRoot
$setupPath = Join-Path $scriptRoot 'rls-app-role-clone-setup.sql'
$verifyPath = Join-Path $scriptRoot 'rls-app-role-clone-verify.sql'
foreach ($file in @($setupPath, $verifyPath)) {
    if (!(Test-Path -LiteralPath $file)) { throw "Missing SQL file: $file" }
}

if (!$BackupFile) {
    $backupDir = Join-Path (Split-Path -Parent $repoRoot) 'MedTour-AI-Backups'
    $candidate = Get-ChildItem -LiteralPath $backupDir -Filter 'medtour-*.dump' -File |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$candidate) { throw "No synthetic development archive found in $backupDir" }
    $BackupFile = $candidate.FullName
}
$BackupFile = (Resolve-Path -LiteralPath $BackupFile).Path
if ((Get-Item -LiteralPath $BackupFile).Length -eq 0) { throw 'Backup file is empty' }

$containerName = 'medtour-role-clone-' + (Get-Date -Format 'yyyyMMddHHmmss') + '-' + $PID
$postgresPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$appPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$started = $false

function AssertDockerExit([string]$message) {
    if ($LASTEXITCODE -ne 0) { throw $message }
}

try {
    Write-Host 'Starting a disposable, network-isolated PostgreSQL 17 clone...'
    docker run -d --rm --network none --name $containerName -e "POSTGRES_PASSWORD=$postgresPassword" postgres:17-alpine | Out-Null
    AssertDockerExit 'Failed to create isolated PostgreSQL'
    $started = $true

    $ready = $false
    for ($i=1; $i -le 40; $i++) {
        docker exec $containerName pg_isready -U postgres -h /var/run/postgresql 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Isolated PostgreSQL failed readiness check' }

    docker cp "$BackupFile" ($containerName + ':/tmp/medtour-backup.dump') | Out-Null
    AssertDockerExit 'Copying synthetic backup failed'
    docker exec $containerName pg_restore --list /tmp/medtour-backup.dump | Out-Null
    AssertDockerExit 'Development backup is not a valid PostgreSQL archive'
    docker exec $containerName createdb -U postgres medtour_role_clone
    AssertDockerExit 'Creating the isolated clone database failed'
    docker exec $containerName pg_restore --single-transaction --no-owner --no-acl -U postgres -d medtour_role_clone /tmp/medtour-backup.dump
    AssertDockerExit 'Restoring the development backup failed'
    Write-Host 'PASS: development backup restored without touching Compose'

    $syntheticIds = @{
        '__TENANT_A__' = [guid]::NewGuid().ToString()
        '__TENANT_B__' = [guid]::NewGuid().ToString()
        '__PATIENT_A__' = [guid]::NewGuid().ToString()
        '__PATIENT_B__' = [guid]::NewGuid().ToString()
    }

    $setupSql = Get-Content -LiteralPath $setupPath -Raw -Encoding UTF8
    $verifySql = Get-Content -LiteralPath $verifyPath -Raw -Encoding UTF8
    foreach ($key in $syntheticIds.Keys) {
        $setupSql = $setupSql.Replace($key, $syntheticIds[$key])
        $verifySql = $verifySql.Replace($key, $syntheticIds[$key])
    }
    $setupSql = $setupSql.Replace('__APP_PASSWORD__', $appPassword)

    # Provision ONLY inside the isolated database using the temporary postgres account.
    $setupSql | docker exec -i $containerName psql -X -v ON_ERROR_STOP=1 -U postgres -d medtour_role_clone
    AssertDockerExit 'Provisioning isolated app role failed'

    # Authenticate over a local TCP socket inside the isolated container.
    # This exercises a real LOGIN role rather than only using SET ROLE.
    $verifySql | docker exec -i -e "PGPASSWORD=$appPassword" $containerName psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U medtour_app -d medtour_role_clone
    AssertDockerExit 'Least-privilege LOGIN role audit failed'

    Write-Host 'PASS: STAGE 19.12 ISOLATED DATABASE LOGIN AND PERMISSIONS AUDIT COMPLETED' -ForegroundColor Green
    Write-Warning 'P0 still open: plain client-settable tenant GUC is spoofable. Do NOT enable RLS on live database or switch live API credentials.'
}
finally {
    if ($started) {
        docker rm -f $containerName 2>$null | Out-Null
    }
}
