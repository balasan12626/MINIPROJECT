param([string]$in,[string]$outDocx,[string]$outPdf)
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($in, $false, $false)
  $d.Fields.Update() | Out-Null
  foreach($t in $d.TablesOfContents){ $t.Update() }
  $d.Repaginate()
  foreach($t in $d.TablesOfContents){ $t.UpdatePageNumbers() }
  $d.SaveAs2([ref]$outDocx, [ref]16)
  $d.SaveAs2([ref]$outPdf, [ref]17)
  "pages: " + $d.ComputeStatistics(2)
  $d.Close([ref]0)
} finally { $w.Quit() }
