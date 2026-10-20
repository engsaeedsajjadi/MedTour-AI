# Stage 19.13: Proof of DB-principal-bound RLS on a restored, disposable PostgreSQL 17 clone.
# All data in the selected backup MUST be synthetic; never provide a PHI backup.
# Does NOT contact Compose services, edit live credentials, or mount live volumes.
param([string]$BackupFile = '')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$setupPath = Join-Path $PSScriptRoot 'rls-db-principal-clone-setup.sql'
$verifyPath = Join-Path $PSScriptRoot 'rls-db-principal-clone-verify.sql'
foreach ($file in @($setupPath, $verifyPath)) {
    if (!(Test-Path -LiteralPath $file)) { throw "Missing SQL input: $file" }
}
if (!$BackupFile) {
    $dir = Join-Path (Split-Path -Parent $repoRoot) 'MedTour-AI-Backups'
    $candidate = Get-ChildItem -LiteralPath $dir -Filter 'medtour-*.dump' -File |
      Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$candidate) { throw "No synthetic-development backup found in $dir" }
    $BackupFile = $candidate.FullName
}
$BackupFile = (Resolve-Path -LiteralPath $BackupFile).Path
if ((Get-Item -LiteralPath $BackupFile).Length -eq 0) { throw 'Backup file is empty' }

$containerName = 'medtour-principal-poc-' + (Get-Date -Format 'yyyyMMddHHmmss') + '-' + $PID
$adminPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$passwordA = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$passwordB = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$started = $false
function AssertDocker([string]$message) {
    if ($LASTEXITCODE -ne 0) { throw $message }
}

try {
    Write-Host 'Creating offline PostgreSQL 17 principal-isolation proof...'
    # Force host SCRAM password authentication, avoiding socket/trust false positives.
    docker run -d --rm --network none --name $containerName -e "POSTGRES_PASSWORD=$adminPassword" -e "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust" postgres:17-alpine | Out-Null
    AssertDocker 'Failed to start isolated PostgreSQL'
    $started = $true

    # Wait for the final TCP postmaster, NOT the temporary initdb Unix socket.
    $ready = $false
    for ($i=1; $i -le 60; $i++) {
        docker exec $containerName pg_isready -h 127.0.0.1 -p 5432 -U postgres -d postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Final PostgreSQL server did not become available' }

    docker cp "$BackupFile" ($containerName + ':/tmp/medtour-synthetic.dump') | Out-Null
    AssertDocker 'Copying synthetic backup failed'
    docker exec $containerName pg_restore --list /tmp/medtour-synthetic.dump | Out-Null
    AssertDocker 'Invalid backup archive'
    docker exec $containerName createdb -U postgres medtour_principal_clone
    AssertDocker 'Failed to create isolated clone database'
    docker exec $containerName pg_restore --single-transaction --no-owner --no-acl -U postgres -d medtour_principal_clone /tmp/medtour-synthetic.dump
    AssertDocker 'Failed restoring synthetic schema'
    Write-Host 'PASS: synthetic backup restored inside network-isolated clone'

    $ids = @{
        '__PASS_A__'=$passwordA
        '__PASS_B__'=$passwordB
        '__TENANT_A__'=[guid]::NewGuid().ToString()
        '__TENANT_B__'=[guid]::NewGuid().ToString()
        '__PATIENT_A__'=[guid]::NewGuid().ToString()
        '__PATIENT_B__'=[guid]::NewGuid().ToString()
    }
    $setupSql = Get-Content -LiteralPath $setupPath -Raw -Encoding UTF8
    foreach ($key in $ids.Keys) { $setupSql = $setupSql.Replace($key,$ids[$key]) }
    $setupSql | docker exec -i $containerName psql -X -v ON_ERROR_STOP=1 -U postgres -d medtour_principal_clone
    AssertDocker 'Protected role and policy provisioning failed'

    foreach ($role in @('mt_clone_a','mt_clone_b')) {
        $expected = if ($role -eq 'mt_clone_a') { $passwordA } else { $passwordB }
        $badPassword = 'not-the-password-' + [guid]::NewGuid().ToString('N')

        # A deliberately invalid password must produce an actual PostgreSQL
        # authentication failure, not a Docker/network error. Handle expected
        # stderr INSIDE the container: Windows PowerShell 5.1 can convert native
        # stderr to a terminating NativeCommandError when ErrorActionPreference=Stop.
        # The shell returns 0 ONLY for the specific expected password denial.
        # Pass the script on STDIN (not as a Windows-native sh -c argument),
        # preserving embedded quote marks and multiline shell syntax.
        $wrongPasswordCheck = @'
result=$(psql -X -h 127.0.0.1 -U "$PGUSER" -d medtour_principal_clone -c 'SELECT 1' 2>&1)
status=$?
if [ "$status" -ne 0 ] && printf '%s' "$result" | grep -q 'password authentication failed'; then
    exit 0
fi
printf '%s\n' "Unexpected wrong-password test result: $result" >&2
exit 1
'@
        $wrongPasswordCheck | docker exec -i -e "PGPASSWORD=$badPassword" -e "PGUSER=$role" $containerName sh | Out-Null
        AssertDocker "Wrong-password denial test did not yield the expected PostgreSQL authentication error for $role"
        Write-Host "PASS: $role rejects an incorrect password"

        $verifySql = Get-Content -LiteralPath $verifyPath -Raw -Encoding UTF8
        if ($role -eq 'mt_clone_a') {
            $otherRole = 'mt_clone_b'
            $ownTenant = $ids['__TENANT_A__']
            $otherTenant = $ids['__TENANT_B__']
            $ownPatient = $ids['__PATIENT_A__']
            $otherPatient = $ids['__PATIENT_B__']
        } else {
            $otherRole = 'mt_clone_a'
            $ownTenant = $ids['__TENANT_B__']
            $otherTenant = $ids['__TENANT_A__']
            $ownPatient = $ids['__PATIENT_B__']
            $otherPatient = $ids['__PATIENT_A__']
        }
        $repl = @{
            '__EXPECTED_ROLE__' = $role
            '__OTHER_ROLE__' = $otherRole
            '__OWN_TENANT__' = $ownTenant
            '__OTHER_TENANT__' = $otherTenant
            '__OWN_PATIENT__' = $ownPatient
            '__OTHER_PATIENT__' = $otherPatient
            '__BLOCKED_PATIENT__' = [guid]::NewGuid().ToString()
        }
        foreach ($key in $repl.Keys) { $verifySql = $verifySql.Replace($key,$repl[$key]) }
        $verifySql | docker exec -i -e "PGPASSWORD=$expected" $containerName psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U $role -d medtour_principal_clone
        AssertDocker "Principal-bound RLS verification failed for $role"
    }

    Write-Host 'PASS: STAGE 19.13 PRINCIPAL-BOUND RLS SECURITY PROOF COMPLETED' -ForegroundColor Green
    Write-Warning 'This is a clone-only proof, NOT the production design. Per-tenant pools, provisioning, revocation and pre-auth services remain to be built and tested.'
}
finally {
    if ($started) { docker rm -f $containerName 2>$null | Out-Null }
}
