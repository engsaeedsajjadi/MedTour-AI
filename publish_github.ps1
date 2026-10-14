# Run in PowerShell after creating a PRIVATE, EMPTY GitHub repository named MedTour-AI.
# This script NEVER creates the remote repository and NEVER force-pushes.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not installed.' }
$remote = 'https://github.com/engsaeedsajjadi/MedTour-AI.git'
if (-not (Test-Path '.git')) { throw 'The project git metadata is missing. Extract the full ZIP, including the .git folder.' }
$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) { git remote add origin $remote }
elseif ($origin -ne $remote) { throw "Origin points to another location: $origin" }
git branch --show-current
git status --short
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed. Confirm GitHub repo exists and you are signed in.' }
Write-Host 'Repository push completed successfully.' -ForegroundColor Green
