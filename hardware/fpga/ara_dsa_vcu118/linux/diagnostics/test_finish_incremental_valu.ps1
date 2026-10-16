#requires -Version 5.1
# Test the actual report gates without running Vivado or touching build outputs.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'finish_incremental_valu.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$try = $ast.EndBlock.Statements | Where-Object { $_ -is [Management.Automation.Language.TryStatementAst] }
$statements = @($try.Body.Statements)
$start = -1
$end = -1
for ($i = 0; $i -lt $statements.Count; $i++) {
    $s = $statements[$i]
    if ($s -is [Management.Automation.Language.AssignmentStatementAst] -and
        $s.Left -is [Management.Automation.Language.VariableExpressionAst] -and
        $s.Left.VariablePath.UserPath -eq 'summary') { $start = $i }
    if ($start -ge 0 -and $s -is [Management.Automation.Language.PipelineAst] -and
        $s.PipelineElements[0] -is [Management.Automation.Language.CommandAst] -and
        $s.PipelineElements[0].GetCommandName() -eq 'State') { $end = $i; break }
}
if ($start -lt 0 -or $end -le $start) { throw 'Report gate block not found' }
$gate = [scriptblock]::Create(($statements[$start..($end-1)] | ForEach-Object { $_.Extent.Text }) -join "`n")
$audit = [pscustomobject]@{Reports='D:\not_a_real_report_directory'}
function Get-Content([string]$LiteralPath, [switch]$Raw) {
    switch (Split-Path -Leaf $LiteralPath) {
        'timing_summary.rpt' { return $script:summaryFixture }
        'drc.rpt' { return $script:drcFixture }
        default { throw 'Unexpected read by report gates' }
    }
}
function Check([string]$name, [string]$row, [string]$drc, [bool]$accept) {
    $script:summaryFixture = "WNS(ns) TNS(ns) endpoints WHS(ns) WPWS(ns)`r`n-------`r`n$row`r`n"
    $script:drcFixture = $drc
    $caught = $false
    try { & $gate } catch { $caught = $true }
    if ($caught -eq $accept) { throw "Unexpected gate result: $name" }
    Write-Host "PASS $name"
}
$valid = '0.001 0.000 0 912834 0.001 0.000 0 911679 0.005 0.000 0 306551'
Check 'valid' $valid '| REQP-1869 | Warning | unused cascade | 96 |' $true
foreach ($column in @(0, 4, 8)) {
    $fields = $valid -split ' '
    $fields[$column] = '-0.001'
    Check "negative_slack_$column" ($fields -join ' ') '' $false
    $fields = $valid -split ' '
    $fields[$column+2] = '1'
    Check "failing_endpoint_$column" ($fields -join ' ') '' $false
    $fields = $valid -split ' '
    $fields[$column+3] = '0'
    Check "missing_endpoints_$column" ($fields -join ' ') '' $false
}
Check 'drc_error' $valid '| MDRV-1 | Error | Multiple drivers | 1 |' $false
Check 'drc_critical' $valid '| TEST-1 | Critical Warning | finding | 1 |' $false
Check 'malformed_summary' '0.001 0.000 0' '' $false
Check 'nonfinite_slack' ($valid -replace '^0.001', 'NaN') '' $false
Write-Host 'REPORT_GATE_TESTS_PASS=14'
