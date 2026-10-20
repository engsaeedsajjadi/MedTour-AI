# Stage 19.20: HTTP-request-bound tenant role routing in FastAPI on offline clone.
# tenant PostgreSQL roles in a disposable restored clone (no live changes).
# This is NOT a live deployment or a production schema migration.
# Backup MUST contain synthetic development data, no real patient information.
param([string]$BackupFile = '', [string]$ApiImage = 'medtour-ai-api')

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$setupPath = Join-Path $PSScriptRoot 'rls-db-principal-clone-setup.sql'
$probePath = Join-Path $PSScriptRoot 'rls-request-bound-fastapi-probe.py'
$seedPath = Join-Path $PSScriptRoot 'rls-fastapi-endpoint-clone-seed.sql'
foreach ($file in @($setupPath, $probePath, $seedPath)) {
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
$networkName = 'medtour-request-isolated-' + $tag
$dbName = 'medtour-request-db-' + $tag
$runnerName = 'medtour-request-runner-' + $tag
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

    # Seed only into the temporary clone with synthetic credentials and identifiers.
    $fixture = @{
        '__TENANT_A__' = $ids['__TENANT_A__']
        '__TENANT_B__' = $ids['__TENANT_B__']
        '__PATIENT_A__' = $ids['__PATIENT_A__']
        '__PATIENT_B__' = $ids['__PATIENT_B__']
        '__USER_A__' = [guid]::NewGuid().ToString()
        '__USER_B__' = [guid]::NewGuid().ToString()
        '__AUDITOR_A__' = [guid]::NewGuid().ToString()
        '__PORTAL_ID_A__' = [guid]::NewGuid().ToString()
        '__PORTAL_ID_B__' = [guid]::NewGuid().ToString()
        '__CONSENT_ID_A__' = [guid]::NewGuid().ToString()
        '__CONSENT_ID_B__' = [guid]::NewGuid().ToString()
        '__REFRESH_ID_A__' = [guid]::NewGuid().ToString()
        '__REFRESH_ID_B__' = [guid]::NewGuid().ToString()
        '__FAMILY_A__' = [guid]::NewGuid().ToString()
        '__FAMILY_B__' = [guid]::NewGuid().ToString()
    }
    $tokens = @{
        'PORTAL_A' = 'synthetic-portal-a-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        'PORTAL_B' = 'synthetic-portal-b-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        'CONSENT_A' = 'synthetic-consent-a-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        'CONSENT_B' = 'synthetic-consent-b-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        'REFRESH_A' = 'synthetic-refresh-a-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        'REFRESH_B' = 'synthetic-refresh-b-' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    }
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        foreach ($k in $tokens.Keys) {
            $hashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($tokens[$k]))
            $fixture['__HASH_' + $k + '__'] = -join ($hashBytes | ForEach-Object { $_.ToString('x2') })
        }
    }
    finally { $sha256.Dispose() }
    $seed = Get-Content -LiteralPath $seedPath -Raw -Encoding UTF8
    foreach ($key in $fixture.Keys) { $seed = $seed.Replace($key,$fixture[$key]) }
    CopySqlToClone $seed '/tmp/medtour-fastapi-seed.sql'
    docker exec $dbName psql -X -v ON_ERROR_STOP=1 -U postgres -d medtour_principal_clone -f /tmp/medtour-fastapi-seed.sql
    AssertDocker 'Failed to seed synthetic FastAPI RLS fixtures'
    Write-Host 'PASS: synthetic user, portal, consent and refresh fixtures seeded'

    # The probe is launched as /tmp/*.py, so Python's script directory is
    # /tmp instead of Dockerfile WORKDIR /app. Include /app on sys.path
    # explicitly without changing the operational API image or source.
    $runnerArgs = @(
        '--name', $runnerName, '--network', $networkName,
        '-e', 'PYTHONPATH=/app',
        '-e', 'PROBE_DB_HOST=medtour-test-db',
        '-e', 'APP_ENV=test',
        '-e', 'DATABASE_URL=sqlite://',
        '-e', 'JWT_SECRET=stage-19-16-synthetic-test-key-very-long-value',
        '-e', "PROBE_PASSWORD_A=$passwordA",
        '-e', "PROBE_PASSWORD_B=$passwordB",
        '-e', "PROBE_TENANT_A=$($ids['__TENANT_A__'])",
        '-e', "PROBE_TENANT_B=$($ids['__TENANT_B__'])",
        '-e', "PROBE_PATIENT_A=$($ids['__PATIENT_A__'])",
        '-e', "PROBE_PATIENT_B=$($ids['__PATIENT_B__'])",
        '-e', "PROBE_USER_A=$($fixture['__USER_A__'])",
        '-e', "PROBE_USER_B=$($fixture['__USER_B__'])",
        '-e', "PROBE_AUDITOR_A=$($fixture['__AUDITOR_A__'])",
        '-e', "PROBE_PORTAL_A=$($tokens['PORTAL_A'])",
        '-e', "PROBE_PORTAL_B=$($tokens['PORTAL_B'])",
        '-e', "PROBE_CONSENT_A=$($tokens['CONSENT_A'])",
        '-e', "PROBE_CONSENT_B=$($tokens['CONSENT_B'])",
        '-e', "PROBE_REFRESH_A=$($tokens['REFRESH_A'])",
        '-e', "PROBE_REFRESH_B=$($tokens['REFRESH_B'])",
        $ApiImage, 'python', '/tmp/rls-request-bound-fastapi-probe.py'
    )
    docker create @runnerArgs | Out-Null
    AssertDocker 'Failed to create isolated Python ORM runner'
    $runnerCreated = $true

    # Install checked-out app code only in this disposable runner. The existing
    # API image can predate this staged module and is not rebuilt/restarted.
    $appDir = Join-Path $repoRoot 'backend/app'
    if (!(Test-Path -LiteralPath $appDir)) { throw "Missing local backend package: $appDir" }
    docker cp $appDir ($runnerName + ':/app/') | Out-Null
    AssertDocker 'Could not copy current backend into isolated test runner'
    docker cp $probePath ($runnerName + ':/tmp/rls-request-bound-fastapi-probe.py') | Out-Null
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
        throw "Request-bound FastAPI tenant routing test failed: exit code $exitCodeText"
    }
    Write-Host 'PASS: STAGE 19.20 ISOLATED REQUEST-BOUND FASTAPI TENANT ROUTING TEST COMPLETED' -ForegroundColor Green
    Write-Warning 'This is a clone-only request-scoped FastAPI dependency override. Production Login, Refresh, Webhook, Alembic and global get_db are not migrated.'
}
finally {
    if ($runnerCreated) { docker rm -f $runnerName 2>$null | Out-Null }
    if ($dbStarted) { docker rm -f $dbName 2>$null | Out-Null }
    if ($networkCreated) { docker network rm $networkName 2>$null | Out-Null }
}
