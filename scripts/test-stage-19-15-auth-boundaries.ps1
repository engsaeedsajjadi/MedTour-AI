# Stage 19.15: run synthetic FastAPI tenant-boundary tests without network
# or access to running MedTour AI services/Compose volumes.
# Requires a previously built local medtour-ai-api Docker image.
param([switch]$FullSuite, [switch]$TokenRoutingOnly, [switch]$AtomicTransactionsOnly, [switch]$HttpRouterOnly, [switch]$PreauthOnly, [switch]$TenantRegistryOnly, [string]$ApiImage = 'medtour-ai-api')
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$testsDir = Join-Path $repoRoot 'backend/tests'
$appDir = Join-Path $repoRoot 'backend/app'
if (!(Test-Path -LiteralPath $appDir)) { throw "Backend package not found: $appDir" }
$stageTest = Join-Path $testsDir 'test_stage_19_15_tenant_auth_boundaries.py'
$tokenTest = Join-Path $testsDir 'test_stage_19_17_tenant_route_tokens.py'
$atomicTest = Join-Path $testsDir 'test_stage_19_19_staged_transactions.py'
$httpTest = Join-Path $testsDir 'test_stage_19_20_http_router.py'
$preauthTest = Join-Path $testsDir 'test_stage_19_21_preauth.py'
$registryTest = Join-Path $testsDir 'test_stage_19_22_tenant_registry.py'
if (@($FullSuite, $TokenRoutingOnly, $AtomicTransactionsOnly, $HttpRouterOnly, $PreauthOnly, $TenantRegistryOnly).Where({ $_ }).Count -gt 1) {
    throw 'Select only one of -FullSuite, -TokenRoutingOnly, -AtomicTransactionsOnly, -HttpRouterOnly, -PreauthOnly or -TenantRegistryOnly'
}
if ($TokenRoutingOnly -and !(Test-Path -LiteralPath $tokenTest)) {
    throw "Token-routing test missing; pull main first: $tokenTest"
}
if ($AtomicTransactionsOnly -and !(Test-Path -LiteralPath $atomicTest)) {
    throw "Atomic transaction test missing; pull main first: $atomicTest"
}
if ($HttpRouterOnly -and !(Test-Path -LiteralPath $httpTest)) {
    throw "HTTP routing test missing; pull main first: $httpTest"
}
if ($PreauthOnly -and !(Test-Path -LiteralPath $preauthTest)) {
    throw "Pre-auth routing test missing; pull main first: $preauthTest"
}
if ($TenantRegistryOnly -and !(Test-Path -LiteralPath $registryTest)) {
    throw "Tenant registry test missing; pull main first: $registryTest"
}
if (!(Test-Path -LiteralPath $stageTest)) {
    throw "Required test missing; pull main before running: $stageTest"
}
docker image inspect $ApiImage --format '{{.Id}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Local API image $ApiImage is unavailable. Run docker compose build api to build the image, then retry."
}

$runner = 'medtour-stage-1915-' + (Get-Date -Format 'yyyyMMddHHmmss') + '-' + $PID
$created = $false
function AssertDocker([string]$message) {
    if ($LASTEXITCODE -ne 0) { throw $message }
}
try {
    $target = if ($FullSuite) {
        '/tmp/medtour-tests'
    } elseif ($TokenRoutingOnly) {
        '/tmp/medtour-tests/test_stage_19_17_tenant_route_tokens.py'
    } elseif ($AtomicTransactionsOnly) {
        '/tmp/medtour-tests/test_stage_19_19_staged_transactions.py'
    } elseif ($HttpRouterOnly) {
        '/tmp/medtour-tests/test_stage_19_20_http_router.py'
    } elseif ($PreauthOnly) {
        '/tmp/medtour-tests/test_stage_19_21_preauth.py'
    } elseif ($TenantRegistryOnly) {
        '/tmp/medtour-tests/test_stage_19_22_tenant_registry.py'
    } else {
        '/tmp/medtour-tests/test_stage_19_15_tenant_auth_boundaries.py'
    }
    # No Docker network, no live database credentials, no Compose volumes.
    $args = @(
        '--name', $runner, '--network', 'none',
        '-e', 'APP_ENV=test', '-e', 'DATABASE_URL=sqlite://',
        '-e', 'PYTHONPATH=/app',
        $ApiImage, 'python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', $target
    )
    docker create @args | Out-Null
    AssertDocker 'Could not create the isolated Python test runner'
    $created = $true

    # Use the checked-out application code rather than a potentially stale
    # pre-existing Docker image. Only the disposable runner receives these files.
    docker cp $appDir ($runner + ':/app/') | Out-Null
    AssertDocker 'Could not copy checked-out backend package to temporary runner'
    docker cp $testsDir ($runner + ':/tmp/medtour-tests') | Out-Null
    AssertDocker 'Could not copy synthetic pytest suite to isolated runner'
    docker start $runner | Out-Null
    AssertDocker 'Could not start isolated test runner'

    $exitCode = docker wait $runner
    AssertDocker 'Failed retrieving isolated test exit status'
    $previousPreference = $ErrorActionPreference
    try {
        # pytest failures generate normal stderr. Print it as diagnostics, not
        # PowerShell NativeCommandError from the intentionally failing assertions.
        $ErrorActionPreference = 'Continue'
        docker logs $runner
    }
    finally { $ErrorActionPreference = $previousPreference }
    if ([int]($exitCode | Select-Object -Last 1) -ne 0) {
        throw "Offline backend security regression tests FAILED (exit $exitCode)"
    }
    if ($FullSuite) {
        Write-Host 'PASS: FULL SYNTHETIC BACKEND TEST SUITE COMPLETED IN OFFLINE CONTAINER' -ForegroundColor Green
    }
    elseif ($TokenRoutingOnly) {
        Write-Host 'PASS: STAGE 19.17 TENANT ROUTING TOKEN UNIT TESTS COMPLETED' -ForegroundColor Green
    }
    elseif ($AtomicTransactionsOnly) {
        Write-Host 'PASS: STAGE 19.19 ATOMIC TRANSACTION UNIT TESTS COMPLETED' -ForegroundColor Green
    }
    elseif ($HttpRouterOnly) {
        Write-Host 'PASS: STAGE 19.20 FAIL-CLOSED HTTP ROUTING UNIT TESTS COMPLETED' -ForegroundColor Green
    }
    elseif ($PreauthOnly) {
        Write-Host 'PASS: STAGE 19.21 PREAUTH FAIL-CLOSED UNIT TESTS COMPLETED' -ForegroundColor Green
    }
    elseif ($TenantRegistryOnly) {
        Write-Host 'PASS: STAGE 19.22 TENANT REGISTRY LEASE AND REVOCATION UNIT TESTS COMPLETED' -ForegroundColor Green
    }
    else {
        Write-Host 'PASS: STAGE 19.15 SYNTHETIC TENANT AUTH BOUNDARY TESTS COMPLETED' -ForegroundColor Green
    }
    Write-Warning 'Only SQLite API regression tests were run. No PostgreSQL RLS/real API role-routing integration has been performed.'
}
finally {
    if ($created) {
        docker rm -f $runner 2>$null | Out-Null
    }
}
