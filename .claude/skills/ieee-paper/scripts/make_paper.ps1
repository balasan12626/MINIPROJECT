# One-command rebuild of the IEEE conference paper (PDF + Word, blind + camera-ready) and the fixes report.
#   .\.claude\skills\ieee-paper\scripts\make_paper.ps1             # full rebuild (re-runs experiments)
#   .\.claude\skills\ieee-paper\scripts\make_paper.ps1 -SkipExp    # reuse <work>\exp.json (text-only edits)
param([switch]$SkipExp)
# "Continue": MiKTeX/npm write harmless warnings to stderr; failures are caught by exit codes (Check) instead.
$ErrorActionPreference = "Continue"
$MaxPages = if ($env:PAPER_MAX_PAGES) { [int]$env:PAPER_MAX_PAGES } else { 8 }  # INDICON: set 6
$Scripts = $PSScriptRoot
$Root = (Resolve-Path "$Scripts\..\..\..\..").Path
$Work = if ($env:PAPER_WORK_DIR) { $env:PAPER_WORK_DIR } else { Join-Path $env:TEMP "aquasentinel-ieee" }
$Out = Join-Path $Root "iee papper fineal\revised"
$Final = Join-Path $Out "FINEL"
$Venv = Join-Path $Root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force $Work, $Out, $Final | Out-Null

function Step($n, $msg) { Write-Host "$n/8 $msg" }
function Check($what) { if ($LASTEXITCODE) { throw "$what failed" } }

if (-not $SkipExp -or -not (Test-Path "$Work\exp.json")) {
  Step 1 "Seeded experiments (benchmark, ablation, closure sweep, failure gating)"
  $env:PYTHONPATH = $Root
  & $Venv "$Scripts\exp.py" $Work; Check "exp.py"
} else { Step 1 "Experiments skipped (reusing $Work\exp.json)" }

$env:PYTHONPATH = $Root
& $Venv "$Scripts\exp_min.py" $Work; Check "exp_min.py"
& $Venv "$Scripts\exp_extra.py" $Work; Check "exp_extra.py"

Step 2 "Fig. 2 chart"
python "$Scripts\figs.py" $Work; Check "figs.py"

Step 3 "Blind + camera-ready LaTeX sources"
python "$Scripts\split_versions.py" $Work; Check "split_versions.py"

Step 4 "pdflatex (IEEEtran)"
Push-Location $Work
try {
  foreach ($f in "blind", "camera") {
    Remove-Item "$f.pdf" -ErrorAction SilentlyContinue
    cmd /c "pdflatex -interaction=nonstopmode $f.tex >nul 2>&1"
    cmd /c "pdflatex -interaction=nonstopmode $f.tex >nul 2>&1"
    if (-not (Test-Path "$f.pdf")) { throw "pdflatex $f failed - see $Work\$f.log" }
  }
} finally { Pop-Location }

Step 5 "Number / format / anonymity checks"
python "$Scripts\verify.py" $Work; Check "verify.py"

Step 6 "Word versions (images, JSON, docx-js)"
python "$Scripts\render_imgs.py" $Work; Check "render_imgs.py"
Push-Location $Work
try {
  if (-not (Test-Path "$Work\node_modules\docx")) { npm install docx --silent --no-audit --no-fund | Out-Null; Check "npm install docx" }
  $env:NODE_PATH = Join-Path $Work "node_modules"
  python "$Scripts\tex2json.py" | Out-Null; Check "tex2json.py"
  node "$Scripts\build_paper_docx.js" blind "SUBMIT_blind_review.docx"; Check "docx blind"
  node "$Scripts\build_paper_docx.js" camera "camera_ready_with_authors.docx"; Check "docx camera"
  node "$Scripts\build_report_docx.js"; Check "report docx"
} finally { Pop-Location }

Step 7 "Word page check"
$w = New-Object -ComObject Word.Application; $w.Visible = $false
try {
  foreach ($n in "SUBMIT_blind_review", "camera_ready_with_authors") {
    $doc = $w.Documents.Open("$Work\$n.docx", $false, $true)
    $p = $doc.ComputeStatistics(2); $doc.Close($false)
    Write-Host "  $n.docx: $p pages"
    if ($p -gt $MaxPages) { throw "$n.docx has $p pages (limit $MaxPages)" }
  }
} finally { $w.Quit() }

Step 8 "Copy to $Out and $Final"
Copy-Item "$Work\blind.pdf" "$Out\SUBMIT_blind_review.pdf" -Force
Copy-Item "$Work\blind.tex" "$Out\SUBMIT_blind_review.tex" -Force
Copy-Item "$Work\camera.pdf" "$Out\camera_ready_with_authors.pdf" -Force
Copy-Item "$Work\camera.tex" "$Out\camera_ready_with_authors.tex" -Force
Copy-Item "$Work\fig_safety.pdf", "$Work\exp.json" $Out -Force
Copy-Item "$Work\SUBMIT_blind_review.docx", "$Work\camera_ready_with_authors.docx", "$Work\INDICON_rejection_issues_and_fixes.docx" $Out -Force
$deliver = "SUBMIT_blind_review.pdf", "SUBMIT_blind_review.docx", "camera_ready_with_authors.pdf", "camera_ready_with_authors.docx", "INDICON_rejection_issues_and_fixes.docx"
foreach ($f in $deliver) { Copy-Item "$Out\$f" $Final -Force }
Compress-Archive -Path ($deliver | ForEach-Object { Join-Path $Out $_ }) -DestinationPath "$Final\For_Guide_Nandhakumar_T.zip" -Force
Copy-Item "$Final\For_Guide_Nandhakumar_T.zip" $Out -Force
Write-Host "Done. Upload: $Final\SUBMIT_blind_review.pdf"
