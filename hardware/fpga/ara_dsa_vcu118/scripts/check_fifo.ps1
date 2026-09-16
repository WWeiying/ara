#requires -Version 5.1
[CmdletBinding()]
param([string]$Vivado = 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Vivado = (Get-Command $Vivado -ErrorAction Stop).Source
if (@(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'").Count) {
    throw 'Vivado processes exist. Inspect/close them before the FIFO check; no process was killed.'
}
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root ('build\fifo_check_' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $out | Out-Null
Write-Host "FIFO-only synthesis; results: $out"
Push-Location -LiteralPath $out
try {
    & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'check_fifo.tcl') `
        -log probe.log -journal probe.jou -tclargs $out
    if ($LASTEXITCODE -ne 0) { throw "FIFO check failed. Inspect $out\probe.log; do not launch the full synthesis." }
} finally { Pop-Location }
