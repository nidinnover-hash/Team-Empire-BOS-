$ErrorActionPreference = "Stop"

Write-Host "Running release gate checks..."
& .\.venv\Scripts\python.exe scripts\check_ready.py
