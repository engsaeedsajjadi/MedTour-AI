# Stage 19.14: Exercise SQLAlchemy ORM and pooled sessions using two authenticated
# tenant PostgreSQL roles in a disposable restored clone.
# This is NOT a live deployment or a production schema migration.
# Backup MUST contain synthetic development data, no real patient information.
param([string]$BackupFile = '', [string]$ApiImage = 'medtour-ai-api')

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$setupPath = Join-Path $PSScriptRoot 'rls-db-principal-clone-setup.sql'
$probePath = Join-Path $PSScriptRoot 'rls-sqlalchemy-pool-probe.py'
foreach ($file in @($setupPath, $probePath)) {
    if (!(Test-Path -LiteralPath $file)) { throw "Missing local test file: $file" }
}
if (!$BackupFile) {
    $backupDir = Join-Path (Split-Path -Parent $repoRoot) 'MedTour-AI-Backups'
    $candidate = Get-ChildItem -LiteralPath $backupDir -Filter 'medtour-*.dump' -File |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$candidate) { throw "No synthetic-development backup found in $backupDir" }
    $BackupFile = $candidate.FullName
}
$BackupFile = (Resolve-Path -LiteralPath $BackupFile).Path
if ((Get-Item -LiteralPath $BackupFile).Length -eq 0) { throw 'Backup archive is empty' }

docker image inspect $ApiImage --format '{{.Id}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The local API test image is not available: $ApiImage. Run docker compose build api, then retry."
}

$tag = (Get-Date -Format 'yyyyMMddHHmmss') + '-' + $PID
$networkName = 'medtour-pool-isolated-' + $tag
$dbName = 'medtour-pool-db-' + $tag
$runnerName = 'medtour-pool-runner-' + $tag
$adminPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$passwordA = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$passwordB = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$networkCreated = $false
$dbStarted = $false
$runnerCreated = $false

function AssertDocker([string]$message) {
    if ($LASTEXITCODE -ne 0) { throw $message }
}
function CopySqlToClone([string]$sqlText, [string]$targetPath) {
    $path = [System.IO.Path]::GetTempFileName()
    try {
        $cr = [string][char]13
        $lf = [string][char]10
        $bytesText = $sqlText.TrimStart([char]0xFEFF).Replace(($cr+$lf),$lf).Replace($cr,$lf)
        [System.IO.File]::WriteAllText($path,$bytesText,[System.Text.UTF8Encoding]::new($false))
        docker cp $path ($dbName + ':' + $targetPath) | Out-Null
        AssertDocker 'Cannot copy setup SQL to isolated PostgreSQL'
    }
    finally { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
}

try {
    docker network create --internal $networkName | Out-Null
    AssertDocker 'Could not create an internal-only Docker network'
    $networkCreated = $true

    docker run -d --rm --network $networkName --network-alias medtour-test-db --name $dbName -e "POSTGRES_PASSWORD=$adminPassword" -e "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust" postgres:17-alpine | Out-Null
    AssertDocker 'Could not create disposable PostgreSQL'
    $dbStarted = $true

    $ready = $false
    for ($i=1; $i -le 60; $i++) {
        docker exec $dbName pg_isready -h 127.0.0.1 -U postgres -d postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Final PostgreSQL server is not ready over TCP' }

    docker cp "$BackupFile" ($dbName + ':/tmp/medtour-synthetic.dump') | Out-Null
    AssertDocker 'Could not copy synthetic backup'
    docker exec $dbName pg_restore --list /tmp/medtour-synthetic.dump | Out-Null
    AssertDocker 'Invalid pg_dump archive'
    docker exec $dbName createdb -U postgres medtour_principal_clone
    AssertDocker 'Could not create temporary database'
    docker exec $dbName pg_restore --single-transaction --no-owner --no-acl -U postgres -d medtour_principal_clone /tmp/medtour-synthetic.dump
    AssertDocker 'Could not restore temporary database'
    Write-Host 'PASS: restored schema in an isolated Docker network'

    $ids = @{
        '__PASS_A__'=$passwordA
        '__PASS_B__'=$passwordB
        '__TENANT_A__'=[guid]::NewGuid().ToString()
        '__TENANT_B__'=[guid]::NewGuid().ToString()
        '__PATIENT_A__'=[guid]::NewGuid().ToString()
        '__PATIENT_B__'=[guid]::NewGuid().ToString()
    }
    $setup = Get-Content -LiteralPath $setupPath -Raw -Encoding UTF8
    foreach ($key in $ids.Keys) { $setup = $setup.Replace($key,$ids[$key]) }
    CopySqlToClone $setup '/tmp/medtour-setup.sql'
    docker exec $dbName psql -X -v ON_ERROR_STOP=1 -U postgres -d medtour_principal_clone -f /tmp/medtour-setup.sql
    AssertDocker 'Isolated role/tenant RLS setup failed'
    Write-Host 'PASS: 37 RLS policies bound to two database LOGIN principals'

    # The probe is launched as /tmp/*.py, so Python's script directory is
    # /tmp instead of Dockerfile WORKDIR /app. Include /app on sys.path
    # explicitly without changing the operational API image or source.
    $runnerArgs = @(
        '--name', $runnerName, '--network', $networkName,
        '-e', 'PYTHONPATH=/app',
        '-e', 'PROBE_DB_HOST=medtour-test-db',
        '-e', "PROBE_PASSWORD_A=$passwordA",
        '-e', "PROBE_PASSWORD_B=$passwordB",
        '-e', "PROBE_TENANT_A=$($ids['__TENANT_A__'])",
        '-e', "PROBE_TENANT_B=$($ids['__TENANT_B__'])",
        '-e', "PROBE_PATIENT_A=$($ids['__PATIENT_A__'])",
        '-e', "PROBE_PATIENT_B=$($ids['__PATIENT_B__'])",
        $ApiImage, 'python', '/tmp/rls-sqlalchemy-pool-probe.py'
    )
    docker create @runnerArgs | Out-Null
    AssertDocker 'Failed to create isolated Python ORM runner'
    $runnerCreated = $true

    docker cp $probePath ($runnerName + ':/tmp/rls-sqlalchemy-pool-probe.py') | Out-Null
    AssertDocker 'Could not copy ORM test into isolated runner'
    docker start $runnerName | Out-Null
    AssertDocker 'Could not start isolated Python ORM runner'

    $exitCodeText = docker wait $runnerName
    AssertDocker 'Could not retrieve the Python ORM test exit code'
    $previousAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        docker logs $runnerName
    }
    finally { $ErrorActionPreference = $previousAction }
    if ([int]($exitCodeText | Select-Object -Last 1) -ne 0) {
        throw "SQLAlchemy tenant-principal test failed: exit code $exitCodeText"
    }
    Write-Host 'PASS: STAGE 19.14 ISOLATED SQLALCHEMY TENANT-PRINCIPAL POOL TEST COMPLETED' -ForegroundColor Green
    Write-Warning 'This is a clone-only ORM proof. Live FastAPI get_db, pre-auth, refresh, portal and webhook remain unchanged.'
}
finally {
    if ($runnerCreated) { docker rm -f $runnerName 2>$null | Out-Null }
    if ($dbStarted) { docker rm -f $dbName 2>$null | Out-Null }
    if ($networkCreated) { docker network rm $networkName 2>$null | Out-Null }
}
