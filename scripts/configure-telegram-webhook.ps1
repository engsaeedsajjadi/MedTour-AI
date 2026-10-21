# Registers ONLY the official Telegram webhook. Never prints credentials or request URLs.
# Requires an official BotFather token + HTTPS domain under operator control.
param(
    [Parameter(Mandatory=$true)][string]$PublicBaseUrl,
    [switch]$Remove
)
$ErrorActionPreference = 'Stop'
$token = $env:TELEGRAM_BOT_TOKEN
$secret = $env:TELEGRAM_WEBHOOK_SECRET
$uri = $null
try { $uri = [uri]$PublicBaseUrl } catch { throw 'Invalid public HTTPS domain' }
if ($uri.Scheme -ne 'https' -or !$uri.Host -or $uri.UserInfo) {
    throw 'A public HTTPS domain without credentials is required'
}
if ($token -notmatch '^[0-9]{6,12}:[A-Za-z0-9_-]{35,}$') {
    throw 'TELEGRAM_BOT_TOKEN must be set to the official BotFather token'
}
if (!$Remove -and $secret -notmatch '^[A-Za-z0-9_-]{32,256}$') {
    throw 'TELEGRAM_WEBHOOK_SECRET must be a random 32-256 character token'
}
if (!$Remove -and !$env:TELEGRAM_BOT_ENABLED) {
    Write-Warning 'Verify that TELEGRAM_BOT_ENABLED=true is set on the destination API server'
}
$body = if ($Remove) {
    @{}
} else {
    @{url=($PublicBaseUrl.TrimEnd('/') + '/api/v1/webhooks/telegram');
      secret_token=$secret; allowed_updates=@('message'); drop_pending_updates=$false}
}
$method = if ($Remove) {'deleteWebhook'} else {'setWebhook'}
try {
    # Official destination only. Never expose URLs carrying the bot token.
    $params = @{
        Method='Post'
        Uri=('https://api.telegram.org/bot' + $token + '/' + $method)
        ContentType='application/json'
        Body=($body | ConvertTo-Json -Compress -Depth 3)
        ErrorAction='Stop'
    }
    $result = Invoke-RestMethod @params
} catch {
    throw 'Telegram API request failed. Check connectivity, BotFather token, HTTPS certificate and eligibility. Credentials are not printed.'
}
if ($result.ok -ne $true) {
    throw 'Telegram API rejected the webhook request. No tokens were printed.'
}
Write-Host $(if ($Remove) {'Telegram webhook removed'} else {'Telegram webhook registered (message updates only)'}) -ForegroundColor Green
