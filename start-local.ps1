param(
    [int]$Port = 8000,
    [string]$Host = "127.0.0.1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Missing virtual environment python at .venv\Scripts\python.exe" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

$envPath = Join-Path $repoRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "Missing .env file in repo root." -ForegroundColor Red
    Write-Host "Create it from .env.example before launching." -ForegroundColor Yellow
    exit 1
}

$envLines = Get-Content $envPath
function Get-EnvValue([string]$key) {
    $line = $envLines | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
    if (-not $line) { return "" }
    $raw = ($line -split "=", 2)[1]
    return $raw.Trim().Trim("'").Trim('"')
}

$secretKey = Get-EnvValue "SECRET_KEY"
$adminPassword = Get-EnvValue "ADMIN_PASSWORD"
$tokenKey = Get-EnvValue "TOKEN_ENCRYPTION_KEY"
$openaiKey = Get-EnvValue "OPENAI_API_KEY"

if ($secretKey.Length -lt 32) {
    Write-Host "SECRET_KEY must be at least 32 characters." -ForegroundColor Red
    exit 1
}
if ($adminPassword.Length -lt 8) {
    Write-Host "ADMIN_PASSWORD must be at least 8 characters." -ForegroundColor Red
    exit 1
}
if ([string]::IsNullOrWhiteSpace($tokenKey)) {
    Write-Host "TOKEN_ENCRYPTION_KEY is required." -ForegroundColor Red
    exit 1
}
if ($tokenKey -eq $secretKey) {
    Write-Host "TOKEN_ENCRYPTION_KEY must be different from SECRET_KEY." -ForegroundColor Red
    exit 1
}
if ([string]::IsNullOrWhiteSpace($openaiKey)) {
    Write-Host "OPENAI_API_KEY is empty. AI features may fail." -ForegroundColor Yellow
}

Write-Host "Starting app at http://$Host`:$Port" -ForegroundColor Green
& $pythonExe -m uvicorn app.main:app --host $Host --port $Port --reload
