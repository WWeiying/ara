param([string]$Root = 'D:\qwen_attention_runs')

$ErrorActionPreference = 'Stop'
$Software = Split-Path -Parent $MyInvocation.MyCommand.Path
$files = @{}
foreach ($mode in @('rvv', 'akv', 'akv_v2')) {
    $file = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter result.csv |
        Where-Object { $_.Directory.Name -like "${mode}_*" } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $file) { throw "missing latest $mode result.csv under $Root" }
    $files[$mode] = $file.FullName
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out = Join-Path $Root "comparison_$stamp.csv"
$json = Join-Path $Root "comparison_$stamp.json"
& py -3 (Join-Path $Software 'compare_attention.py') `
    --rvv $files.rvv --akv $files.akv --akv-v2 $files.akv_v2 `
    --output $out --json $json
Write-Host "Saved: $out"
Write-Host "Saved: $json"
