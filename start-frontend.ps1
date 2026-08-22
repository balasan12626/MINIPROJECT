$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\frontend
Write-Host "Starting Vite on :5173"
npm run dev
