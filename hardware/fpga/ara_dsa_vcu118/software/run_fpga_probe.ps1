param(
    [string]$Port = 'COM6',
    [string]$Root = 'D:\fpga_probe_runs',
    [int]$Seconds = 30,
    [ValidateSet('boot', 'quant')]
    [string]$Probe = 'boot',
    [switch]$WaitForReset
)

$ErrorActionPreference = 'Stop'
$Software = Split-Path -Parent $MyInvocation.MyCommand.Path
$Loader = Join-Path $Software 'uart_load.py'
$Elf = Join-Path $Software "fpga_probe\${Probe}_probe.elf"
if (-not (Test-Path -LiteralPath $Elf)) {
    throw "probe ELF not found: $Elf"
}

$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Run = Join-Path $Root "${Probe}_$Stamp"
$Raw = Join-Path $Run 'raw.log'
New-Item -ItemType Directory -Force -Path $Run | Out-Null

Write-Host "Run: $Run"
$ElfHash = (Get-FileHash -Algorithm SHA256 $Elf).Hash
$ElfHash | Out-File (Join-Path $Run 'elf.sha256') -Encoding ascii
if ($WaitForReset) {
    Write-Host 'Reset the FPGA CPU in Vivado VIO, then press Enter.'
    [Console]::ReadLine() | Out-Null
}

& py -3 $Loader --port $Port --baud 115200 --elf $Elf --chunk-size 4096 --seconds $Seconds 2>&1 |
    Tee-Object -FilePath $Raw
$LoadExit = $LASTEXITCODE
[string]$Text = Get-Content -LiteralPath $Raw -Raw
$Marker = if ($Probe -eq 'quant') { 'QUANT_PROBE PASS' } else { 'FPGA_PROBE 5 quantize_done' }
$Complete = ($LoadExit -eq 0) -and $Text.Contains($Marker)
$LastStage = @($Text -split '\r?\n' | Where-Object {
    $_ -match '^(Q\d\d[A-Za-z]? |QUANT_PROBE |FPGA_PROBE )'
}) | Select-Object -Last 1
[ordered]@{
    probe = $Probe
    elf_sha256 = $ElfHash
    port = $Port
    baud = 115200
    load_exit_code = $LoadExit
    complete = $Complete
    last_stage = $LastStage
} | ConvertTo-Json | Set-Content (Join-Path $Run 'status.json') -Encoding ascii
Write-Host "Saved: $Raw"
if ($LoadExit -ne 0) {
    throw "FPGA probe failed; inspect $Raw"
}
if (-not $Complete) {
    throw "Probe incomplete (not PASS). Last stage: $LastStage. Inspect $Raw"
}
