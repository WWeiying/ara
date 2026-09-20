param(
    [ValidateSet('rvv', 'akv', 'akv_v2')]
    [string]$Mode = 'rvv',
    [string]$Port = 'COM6',
    [string]$Root = 'D:\qwen_attention_runs',
    [int]$Seconds = 30,
    [switch]$WaitForReset
)

$ErrorActionPreference = 'Stop'
$Software = Split-Path -Parent $MyInvocation.MyCommand.Path
$Loader = Join-Path $Software 'uart_load.py'
$Summarizer = Join-Path $Software 'summarize_operator.py'
$Elf = Join-Path $Software "qwen_attention_small\$Mode.elf"
if (-not (Test-Path -LiteralPath $Elf)) {
    throw "benchmark ELF not found: $Elf"
}

$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Run = Join-Path $Root "${Mode}_$Stamp"
New-Item -ItemType Directory -Force -Path $Run | Out-Null
$Raw = Join-Path $Run 'raw.log'
$Csv = Join-Path $Run 'result.csv'
$Json = Join-Path $Run 'result.json'

Write-Host "Run: $Run"
if ($WaitForReset) {
    Write-Host 'Reset the FPGA CPU in Vivado VIO, then press Enter.'
    [Console]::ReadLine() | Out-Null
}

& py -3 $Loader --port $Port --baud 115200 --elf $Elf --no-readback --chunk-size 65536 --seconds $Seconds 2>&1 |
    Tee-Object -FilePath $Raw
if ($LASTEXITCODE -ne 0) {
    throw "UART benchmark failed; inspect $Raw"
}

& py -3 $Summarizer --log $Raw --output $Csv --json $Json --mode $Mode
Get-FileHash -Algorithm SHA256 $Elf | Out-File (Join-Path $Run 'elf.sha256') -Encoding ascii
Write-Host "Saved: $Raw"
Write-Host "Saved: $Csv"
Write-Host "Saved: $Json"
