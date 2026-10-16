param([Parameter(Mandatory=$true)][string]$Bundle)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Bundle=(Resolve-Path -LiteralPath $Bundle).Path
$package=Join-Path $Bundle 'package'
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o);
      ProcessId=$PID; BoardModified=$false; HardwareValidated=$false} |
      ConvertTo-Json | Set-Content (Join-Path $Bundle 'state.json') -Encoding UTF8
}
function Verify {
    & py -3 "$package\scripts\verify_package.py"
    if ($LASTEXITCODE -ne 0) {throw 'Input verification failed'}
    if ((Get-FileHash "$package\SHA256SUMS").Hash -ne $inventory) {
        throw 'Inventory changed'
    }
}
Start-Transcript -LiteralPath (Join-Path $Bundle 'flow.log') -NoClobber
try {
    $inventory=(Get-FileHash "$package\SHA256SUMS").Hash
    State 'verify_inputs'
    Verify
    State 'prepare_ip'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\create_profile.ps1" -Profile host_ethernet
    if ($LASTEXITCODE -ne 0) {throw 'IP preparation failed'}
    Verify
    State 'synthesis'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\run.ps1" -Profile host_ethernet -Stage synth -RunRoot "$Bundle\runs"
    if ($LASTEXITCODE -ne 0) {throw 'Synthesis or timing gate failed'}
    Verify
    State 'synthesis_passed_requires_mmu_netlist_review' 'Check repaired PPN and timing before implementation'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    Stop-Transcript
}
