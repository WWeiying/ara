# Observation-only post-route closure; never programs the board.
#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$package = 'D:\fpga_runs\ara_mainrtl_20260930\package'
$checkpoint = 'D:\fpga_runs\ara_stall_ila_implementation_20261002_03\physical\routed.dcp'
$source = Join-Path $PSScriptRoot 'close_routed_setup.tcl'
if (Test-Path -LiteralPath $Out) { throw 'Output already exists' }
if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {
    throw 'Another Vivado process is active'
}
if ((Get-FileHash "$package\SHA256SUMS").Hash.ToLower() -ne
    '9dfee610630bfc5f1087ba687a05e946623abd4d569ff7417c6565f9e1cb61dd') {
    throw 'Frozen package inventory changed'
}
& py -3 "$package\scripts\verify_package.py"
if ($LASTEXITCODE -ne 0) { throw 'Frozen package verification failed' }
$inputHash = (Get-FileHash $checkpoint).Hash
$gateHash = (Get-FileHash "$package\scripts\run_support.tcl").Hash
New-Item -ItemType Directory -Path $Out | Out-Null
Copy-Item $source (Join-Path $Out 'close_routed_setup.tcl')
$script = Join-Path $Out 'close_routed_setup.tcl'
$toolHash = (Get-FileHash $script).Hash
@{Checkpoint=$checkpoint; SHA256=$inputHash; GateSHA256=$gateHash;
  ToolSHA256=$toolHash; FunctionalRTLModified=$false; AutomaticProgramming=$false} |
    ConvertTo-Json | Set-Content (Join-Path $Out 'inputs.json') -Encoding UTF8
function State([string]$stage, [string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o);
      ProcessId=$PID; BoardModified=$false; HardwareValidated=$false} |
        ConvertTo-Json | Set-Content (Join-Path $Out 'state.json') -Encoding UTF8
}
try {
    $env:ARA_FPGA_PROFILE = 'host_ethernet'
    Set-Location $Out
    State 'postroute_closure'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -log (Join-Path $Out 'vivado.log') -source $script `
        -tclargs $checkpoint $Out $package
    if ($LASTEXITCODE -ne 0) { throw 'Post-route timing closure failed' }
    if ((Get-Content (Join-Path $Out 'stage.txt') -Raw).Trim() -ne
        'timing_passed_needs_full_audit') { throw 'Completion marker missing' }
    if ((Get-FileHash $checkpoint).Hash -ne $inputHash -or
        (Get-FileHash "$package\scripts\run_support.tcl").Hash -ne $gateHash -or
        (Get-FileHash $script).Hash -ne $toolHash) { throw 'Input changed during closure' }
    Get-FileHash (Join-Path $Out 'ara_dsa_vcu118_routed.dcp') | ConvertTo-Json |
        Set-Content (Join-Path $Out 'output_hash.json') -Encoding UTF8
    State 'timing_passed_needs_full_audit'
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
}
