param(
    [string]$Port = 'COM6',
    [string]$Root = 'D:\fpga_probe_runs',
    [int]$Seconds = 30,
    [switch]$WaitForReset
)

$ErrorActionPreference = 'Stop'
$Software = Split-Path -Parent $MyInvocation.MyCommand.Path
$Loader = Join-Path $Software 'uart_load.py'
$Elf = Join-Path $Software 'fpga_probe\boot_probe.elf'
if (-not (Test-Path -LiteralPath $Elf)) {
    throw "probe ELF not found: $Elf"
}

$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Run = Join-Path $Root "probe_$Stamp"
$Raw = Join-Path $Run 'raw.log'
New-Item -ItemType Directory -Force -Path $Run | Out-Null

Write-Host "Run: $Run"
if ($WaitForReset) {
    Write-Host 'Reset the FPGA CPU in Vivado VIO, then press Enter.'
    [Console]::ReadLine() | Out-Null
}

& py -3 $Loader --port $Port --baud 115200 --elf $Elf --no-readback --chunk-size 65536 --seconds $Seconds 2>&1 |
    Tee-Object -FilePath $Raw
if ($LASTEXITCODE -ne 0) {
    throw "FPGA probe failed; inspect $Raw"
}
Get-FileHash -Algorithm SHA256 $Elf | Out-File (Join-Path $Run 'elf.sha256') -Encoding ascii
Write-Host "Saved: $Raw"
