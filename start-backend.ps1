$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot
$env:FLOOD_LIVE_TICKER = "1"
Write-Host "Starting FastAPI on :8000"
$py = if (Test-Path "$PSScriptRoot\.venv\Scripts\python.exe") { "$PSScriptRoot\.venv\Scripts\python.exe" } else { "python" }
& $py -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3
