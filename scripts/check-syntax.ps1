$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
  'C:\AI-LAB\screenshot-to-code\scripts\start-s2c.ps1', [ref]$null, [ref]$errs)
if ($errs.Count -eq 0) { Write-Output 'parse OK' }
else { $errs | ForEach-Object { Write-Output $_.Message } }
