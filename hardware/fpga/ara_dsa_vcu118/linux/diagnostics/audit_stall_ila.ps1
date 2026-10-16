#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$closure='D:\fpga_runs\ara_stall_ila_closure_20261002_02'
$package='D:\fpga_runs\ara_mainrtl_20260930\package'
$checkpoint=Join-Path $closure 'ara_dsa_vcu118_routed.dcp'
if (Test-Path $Out) { throw 'Output already exists' }
if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {
    throw 'Another Vivado process is active'
}
$state=Get-Content "$closure\state.json" -Raw | ConvertFrom-Json
if ($state.Stage -ne 'timing_passed_needs_full_audit') { throw 'Closure is incomplete' }
$expected=Get-Content "$closure\output_hash.json" -Raw | ConvertFrom-Json
$hash=(Get-FileHash $checkpoint).Hash
if ($hash -ne $expected.Hash) { throw 'Checkpoint hash mismatch' }
if ((Get-FileHash "$package\SHA256SUMS").Hash.ToLower() -ne
    '9dfee610630bfc5f1087ba687a05e946623abd4d569ff7417c6565f9e1cb61dd') {
    throw 'Frozen package inventory changed'
}
& py -3 "$package\scripts\verify_package.py"
if ($LASTEXITCODE -ne 0) { throw 'Frozen package verification failed' }
New-Item -ItemType Directory -Path $Out | Out-Null
$token=[Guid]::NewGuid().ToString('N').Substring(0,12)
Copy-Item (Join-Path $PSScriptRoot 'audit_stall_ila.tcl') $Out
$script=Join-Path $Out 'audit_stall_ila.tcl'
$scriptHash=(Get-FileHash $script).Hash
@{Checkpoint=$checkpoint; SHA256=$hash; Token=$token; ScriptSHA256=$scriptHash;
  Reports="$package\reports\audit_$token"; BoardModified=$false} |
    ConvertTo-Json | Set-Content "$Out\inputs.json" -Encoding UTF8
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; ProcessId=$PID; Updated=(Get-Date -Format o);
      BoardModified=$false; BitstreamGenerated=$false; ManualReviewRequired=$true} |
        ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
}
try {
    State 'auditing'
    Set-Location $Out
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -log "$Out\vivado.log" -source $script -tclargs $checkpoint $package $Out $token
    if ($LASTEXITCODE -ne 0) { throw 'Audit failed' }
    if ((Get-Content "$Out\completed_audit.txt" -Raw).Trim() -ne "audit_$token") {
        throw 'Audit completion marker missing'
    }
    if ((Get-FileHash $checkpoint).Hash -ne $hash -or
        (Get-FileHash $script).Hash -ne $scriptHash) { throw 'Audit input changed' }
    State 'reports_ready_for_manual_review'
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
}
