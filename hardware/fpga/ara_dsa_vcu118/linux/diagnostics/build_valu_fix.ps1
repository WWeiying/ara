# Detached driver: freeze one package, prepare IP, then synthesize with gates.
param([Parameter(Mandatory=$true)][string]$Bundle)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Bundle=(Resolve-Path -LiteralPath $Bundle).Path
$package=Join-Path $Bundle 'package'
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o);
      ProcessId=$PID; BoardModified=$false; Profile='host_ethernet'} |
      ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Bundle 'state.json') -Encoding UTF8
}
function Check-Package {
    & py -3 "$package\scripts\verify_package.py"
    if ($LASTEXITCODE -ne 0) {throw 'Package verification failed'}
    if ((Get-FileHash "$package\SHA256SUMS").Hash -ne $inventory) {throw 'Inventory changed'}
}
Start-Transcript -LiteralPath (Join-Path $Bundle 'flow.log') -NoClobber
try {
    $inventory=(Get-FileHash "$package\SHA256SUMS").Hash
    State 'verify_inputs'
    Check-Package
    State 'prepare_ip'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\create_profile.ps1" -Profile host_ethernet
    if ($LASTEXITCODE -ne 0) {throw 'IP preparation failed; inspect flow.log'}
    Check-Package
    State 'synthesis'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\run.ps1" -Profile host_ethernet -Stage synth -RunRoot "$Bundle\runs"
    if ($LASTEXITCODE -ne 0) {throw 'Synthesis or synthesis gate failed; preserved reports require review'}
    Check-Package
    State 'synthesis_passed_requires_netlist_review' 'Verify full-design VALU and timing before physical continuation'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    Stop-Transcript
}
