Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Missing .venv python. Run: python -m venv .venv" -ForegroundColor Red
    exit 1
}

Write-Host "== Week 1 Quality Sprint ==" -ForegroundColor Cyan

Write-Host "[1/5] Owner hardening..." -ForegroundColor Yellow
& $pythonExe scripts/harden_owner_account.py

Write-Host "[2/5] Config safety tests..." -ForegroundColor Yellow
& $pythonExe -m pytest -q tests/test_config_validation.py tests/test_auth_policy_enforcement.py

Write-Host "[3/5] Core reliability tests..." -ForegroundColor Yellow
& $pythonExe -m pytest -q tests/test_sync_scheduler.py tests/test_github_integration.py tests/test_memory_layers.py

Write-Host "[4/5] Typed checks..." -ForegroundColor Yellow
& $pythonExe -m mypy app/main.py app/services/memory.py app/services/sync_scheduler.py app/services/github_service.py app/core/config.py

Write-Host "[5/5] Dependency integrity..." -ForegroundColor Yellow
& $pythonExe -m pip check

Write-Host "Week 1 quality sprint completed successfully." -ForegroundColor Green

