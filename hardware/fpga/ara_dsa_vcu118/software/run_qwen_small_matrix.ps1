param(
    [string]$Port = 'COM6',
    [string]$Root = 'D:\qwen_small_matrix_runs',
    [int]$Seconds = 30,
    [switch]$WaitForReset
)

$ErrorActionPreference = 'Stop'
$Software = Split-Path -Parent $MyInvocation.MyCommand.Path
$Loader = Join-Path $Software 'uart_load.py'
$BenchParser = Join-Path $Software 'summarize_bench.py'
$OperatorParser = Join-Path $Software 'summarize_operator.py'
$CombinedParser = Join-Path $Software 'summarize_qwen_combined.py'
$MatrixParser = Join-Path $Software 'summarize_qwen_small_matrix.py'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Run = Join-Path $Root "matrix_$Stamp"
$Csv = @{}

New-Item -ItemType Directory -Force -Path $Run | Out-Null

function Invoke-Case {
    param(
        [string]$Name,
        [string]$Elf,
        [string]$Parser,
        [string]$ParserMode,
        [string]$ParserKind
    )
    if (-not (Test-Path -LiteralPath $Elf)) {
        throw "benchmark ELF not found: $Elf"
    }
    $CaseDir = Join-Path $Run $Name
    New-Item -ItemType Directory -Force -Path $CaseDir | Out-Null
    $Raw = Join-Path $CaseDir 'raw.log'
    $OutCsv = Join-Path $CaseDir 'result.csv'
    $OutJson = Join-Path $CaseDir 'result.json'
    Write-Host "`n=== $Name ==="
    if ($WaitForReset) {
        Write-Host 'Reset the FPGA CPU in Vivado VIO, then press Enter.'
        [Console]::ReadLine() | Out-Null
    }
    & py -3 $Loader --port $Port --baud 115200 --elf $Elf --no-readback `
        --chunk-size 65536 --seconds $Seconds 2>&1 |
        Tee-Object -FilePath $Raw | ForEach-Object { $_ | Out-Host }
    if ($LASTEXITCODE -ne 0) {
        throw "UART benchmark failed; inspect $Raw"
    }
    if ($ParserKind -eq 'bench') {
        & py -3 $Parser --log $Raw --output $OutCsv --json $OutJson --mode $ParserMode
    } elseif ($ParserKind -eq 'operator') {
        & py -3 $Parser --log $Raw --output $OutCsv --json $OutJson --mode $ParserMode
    } else {
        & py -3 $Parser --log $Raw --output $OutCsv --json $OutJson
    }
    if ($LASTEXITCODE -ne 0) {
        throw "result parser failed; inspect $Raw"
    }
    Get-FileHash -Algorithm SHA256 $Elf |
        Out-File (Join-Path $CaseDir 'elf.sha256') -Encoding ascii
    $script:Csv[$Name] = $OutCsv
}

$Qwen = Join-Path $Software 'qwen_small'
$Attention = Join-Path $Software 'qwen_attention_small'
$Combined = Join-Path $Software 'qwen_small_combined'

Invoke-Case 'projection_rvv' (Join-Path $Qwen 'rvv.elf') $BenchParser 'rvv' 'bench'
Invoke-Case 'projection_qbs' (Join-Path $Qwen 'qbs.elf') $BenchParser 'qbs' 'bench'
Invoke-Case 'attention_rvv' (Join-Path $Attention 'rvv.elf') $OperatorParser 'rvv' 'operator'
Invoke-Case 'attention_akv_v2' (Join-Path $Attention 'akv_v2.elf') $OperatorParser 'akv_v2' 'operator'
Invoke-Case 'combined_qbs_akv' (Join-Path $Combined 'qbs_akv.elf') $CombinedParser '' 'combined'

$MatrixCsv = Join-Path $Run 'matrix.csv'
$MatrixJson = Join-Path $Run 'matrix.json'
& py -3 $MatrixParser `
    --projection-rvv $Csv['projection_rvv'] `
    --projection-qbs $Csv['projection_qbs'] `
    --attention-rvv $Csv['attention_rvv'] `
    --attention-akv-v2 $Csv['attention_akv_v2'] `
    --combined $Csv['combined_qbs_akv'] `
    --output $MatrixCsv --json $MatrixJson
if ($LASTEXITCODE -ne 0) {
    throw 'matrix parser failed'
}

@{
    port = $Port
    baud = 115200
    bitstream_clock_mhz = 50
    seconds_per_case = $Seconds
    cases = @('rvv', 'qbs', 'akv', 'qbs_akv')
    source_records = $Csv
} | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $Run 'manifest.json') -Encoding ascii

Write-Host "`nSaved matrix: $MatrixCsv"
Write-Host "Saved matrix JSON: $MatrixJson"
Write-Host "Run directory: $Run"
