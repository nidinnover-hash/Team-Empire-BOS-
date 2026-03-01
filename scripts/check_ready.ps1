$ErrorActionPreference = "Stop"

Write-Host "Running release gate checks..."
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3.12 scripts\check_ready.py
} elseif (Test-Path ".\.venv312\Scripts\python.exe") {
  & .\.venv312\Scripts\python.exe scripts\check_ready.py
} elseif (Test-Path ".\.venv\Scripts\python.exe") {
  & .\.venv\Scripts\python.exe scripts\check_ready.py
} else {
  throw "Python 3.12 runtime not found. Install Python 3.12 and retry."
}
