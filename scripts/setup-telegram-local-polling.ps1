# Configure a single authorized development chat for local Telegram polling.
# Prompts for the BotFather token without printing it. The token IS stored in
# the ignored local .env file for Docker Compose; treat that file as secret.
# Never use this mode for real patient information or production.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $project '.env'
if (!(Test-Path $envPath)) {
    Write-Host 'FAIL: Missing .env; create it from .env.example first' -ForegroundColor Red
    exit 1
}

$ptr = [IntPtr]::Zero
$token = $null
$api = $null
try {
    $secure = Read-Host 'Telegram Bot Token' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)

    if ($token -notmatch '^[0-9]{6,12}:[A-Za-z0-9_-]{35,}$') {
        throw 'token-format'
    }
    $api = 'https://api.telegram.org/bot' + $token
    $me = Invoke-RestMethod -Uri ($api + '/getMe') -TimeoutSec 20 -ErrorAction Stop
    if (!$me.ok -or $me.result.username -ne 'MedTourAI_Assistant_Bot') {
        throw 'bot-identity'
    }
    $webhook = Invoke-RestMethod -Uri ($api + '/getWebhookInfo') -TimeoutSec 20 -ErrorAction Stop
    if ($webhook.result.url) {
        throw 'webhook-active'
    }
    Write-Host 'PASS: Correct bot and no active webhook' -ForegroundColor Green

    $initial = Invoke-RestMethod -Method Post -Uri ($api + '/getUpdates') `
        -Body '{"timeout":0,"limit":100}' -ContentType 'application/json' `
        -TimeoutSec 20 -ErrorAction Stop
    if (!$initial.ok) { throw 'telegram-api' }

    $offset = [long]0
    foreach ($item in @($initial.result)) {
        if ($null -eq $item) { continue }
        $offset = [Math]::Max($offset, ([long]$item.update_id + 1))
    }

    $challenge = 'MT-POLL-' + [Guid]::NewGuid().ToString('N').Substring(0, 10).ToUpperInvariant()
    Write-Host ''
    Write-Host 'Send this EXACT NEW message to @MedTourAI_Assistant_Bot:' -ForegroundColor Yellow
    Write-Host $challenge -ForegroundColor Cyan
    Write-Host 'LISTENING: verifying the private test chat...' -ForegroundColor Yellow

    $chatId = $null
    for ($i = 0; $i -lt 8 -and $null -eq $chatId; $i++) {
        $body = @{
            offset = $offset
            timeout = 15
            limit = 100
            allowed_updates = @('message')
        } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -Method Post -Uri ($api + '/getUpdates') `
            -ContentType 'application/json' -Body $body -TimeoutSec 25 -ErrorAction Stop
        if (!$response.ok) { throw 'telegram-api' }
        foreach ($item in @($response.result)) {
            if ($null -eq $item) { continue }
            $offset = [Math]::Max($offset, ([long]$item.update_id + 1))
            $message = $item.message
            if (
                $message -and $message.chat.type -eq 'private' -and
                $message.text -ceq $challenge -and
                [long]$message.chat.id -gt 0 -and
                [long]$message.from.id -eq [long]$message.chat.id
            ) {
                $chatId = [long]$message.chat.id
                break
            }
        }
    }
    if ($null -eq $chatId) {
        Write-Host 'FAIL: Challenge not received; no configuration was changed' -ForegroundColor Red
        exit 1
    }
    Write-Host 'PASS: Authorized private test chat verified' -ForegroundColor Green

    # Only after verifying the challenge: store local settings. Never print them.
    $changes = @{
        APP_ENV = 'development'
        TELEGRAM_BOT_ENABLED = 'false'
        TELEGRAM_POLLING_ENABLED = 'true'
        TELEGRAM_POLLING_TEST_MODE = 'true'
        TELEGRAM_POLLING_CHAT_ID = [string]$chatId
        TELEGRAM_BOT_TOKEN = $token
    }
    $seen = @{}
    $lines = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in [IO.File]::ReadAllLines($envPath)) {
        $handled = $false
        foreach ($key in $changes.Keys) {
            if ($line.StartsWith(($key + '='), [StringComparison]::Ordinal)) {
                $lines.Add($key + '=' + $changes[$key])
                $seen[$key] = $true
                $handled = $true
                break
            }
        }
        if (!$handled) { $lines.Add($line) }
    }
    foreach ($key in $changes.Keys) {
        if (!$seen.ContainsKey($key)) {
            $lines.Add($key + '=' + $changes[$key])
        }
    }
    [IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'PASS: Local allowlisted Telegram polling settings saved in ignored .env' -ForegroundColor Green
    Write-Host 'SECURITY: This mode is development-only; no patient information is allowed' -ForegroundColor Yellow
    Write-Host 'SECURITY: Rotate this previously disclosed token before public deployment' -ForegroundColor Yellow
} catch {
    # Raw REST error output can include a Bot API URL containing the token.
    Write-Host 'FAIL: Telegram verification or local setup failed (details withheld to protect token)' -ForegroundColor Red
    exit 1
} finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    Remove-Variable token, secure, api -ErrorAction SilentlyContinue
}
