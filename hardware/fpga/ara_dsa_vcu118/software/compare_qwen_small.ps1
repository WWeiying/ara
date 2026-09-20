param(
    [string]$Root = 'D:\qwen_small_runs',
    [string]$Output = ''
)

$ErrorActionPreference = 'Stop'
$Software = Split-Path -Parent $MyInvocation.MyCommand.Path
$Comparer = Join-Path $Software 'compare_bench.py'
$Rvv = Get-ChildItem -LiteralPath $Root -Directory -Filter 'rvv_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$Qbs = Get-ChildItem -LiteralPath $Root -Directory -Filter 'qbs_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Rvv -or -not $Qbs) {
    throw "need one RVV run and one QBS run under $Root"
}
$RvvCsv = Join-Path $Rvv.FullName 'result.csv'
$QbsCsv = Join-Path $Qbs.FullName 'result.csv'
if (-not (Test-Path -LiteralPath $RvvCsv) -or -not (Test-Path -LiteralPath $QbsCsv)) {
    throw "latest RVV/QBS run is missing result.csv"
}
if (-not $Output) {
    $Output = Join-Path $Root 'comparison.csv'
}
$Json = [System.IO.Path]::ChangeExtension($Output, '.json')
& py -3 $Comparer --rvv $RvvCsv --qbs $QbsCsv --output $Output --json $Json --clock-mhz 50
Write-Host "RVV: $RvvCsv"
Write-Host "QBS: $QbsCsv"
Write-Host "CSV: $Output"
Write-Host "JSON: $Json"
