$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot
$env:FLOOD_LIVE_TICKER = "1"
Write-Host "Starting FastAPI on :8000"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
