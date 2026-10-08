# One-command rebuild of the project report.
#   .\.claude\skills\project-report\scripts\make_report.ps1              # rebuild, reuse existing screenshots
#   .\.claude\skills\project-report\scripts\make_report.ps1 -Screenshots # also start the app and recapture UI screens
param([switch]$Screenshots)
$ErrorActionPreference = "Stop"
$Scripts = $PSScriptRoot
$Root = (Resolve-Path "$Scripts\..\..\..\..").Path
$Work = if ($env:REPORT_WORK_DIR) { $env:REPORT_WORK_DIR } else { Join-Path $env:TEMP "aquasentinel-report" }
$ReportDir = Join-Path $Root "MINI PROIOJECTT  REPOT FINEL"
$Venv = Join-Path $Root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force (Join-Path $Work "fig") | Out-Null

Write-Host "1/5 HQRL benchmark (seed 42)"
$env:PYTHONPATH = $Root
& $Venv "$Scripts\hqrl_bench.py"; if ($LASTEXITCODE) { throw "hqrl_bench failed" }

Write-Host "2/5 Figures from models/*.json"
python "$Scripts\figs.py"; if ($LASTEXITCODE) { throw "figs failed" }

if ($Screenshots) {
  Write-Host "3/5 Screenshots (starting backend + frontend)"
  $be = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $Root $Venv "-m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
  $fe = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory (Join-Path $Root "frontend") "cmd.exe" "/c npm run dev"
  try {
    $ok = $false
    for ($i = 0; $i -lt 90 -and -not $ok; $i++) {
      Start-Sleep 1
      try { $null = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health; $null = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/; $ok = $true } catch {}
    }
    if (-not $ok) { throw "app did not start (is MongoDB running on 27017?)" }
    node "$Scripts\screenshots.mjs" $Work; if ($LASTEXITCODE) { throw "screenshots failed" }
  } finally {
    Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*vite*" -and $_.CommandLine -like "*fineal mini proejct*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $fe.Id -Force -ErrorAction SilentlyContinue
  }
} else { Write-Host "3/5 Screenshots skipped (reusing $Work\fig\ui_*.png if present)" }

Write-Host "4/5 Build docx from the college sample"
python "$Scripts\build.py"; if ($LASTEXITCODE) { throw "build failed" }

Write-Host "5/5 Word: update TOC / lists, export docx + pdf"
$docx = Join-Path $ReportDir "AquaSentinel_Project_Report.docx"
$pdf = Join-Path $ReportDir "AquaSentinel_Project_Report.pdf"
& "$Scripts\finalize.ps1" (Join-Path $Work "report_raw.docx") $docx $pdf
Write-Host "Done:`n  $docx`n  $pdf"
