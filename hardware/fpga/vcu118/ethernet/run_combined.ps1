# Run only from a frozen combined bundle. Never program or reset the board.
param([ValidateSet('synth', 'all')][string]$Stage = 'synth')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$package = Join-Path $root 'package'
$state = Join-Path $root 'state.json'
if (Test-Path -LiteralPath $state) { throw 'Existing flow state; inspect it instead of restarting' }
function Set-Stage([string]$Stage, [string]$Message = '') {
    $record = @{ Stage = $Stage; Updated = (Get-Date -Format o); Message = $Message;
                 Profile = 'host_ethernet'; BoardModified = $false; ProcessId = $PID }
    $record | ConvertTo-Json | Set-Content -LiteralPath "$state.tmp" -Encoding UTF8
    Move-Item -LiteralPath "$state.tmp" -Destination $state -Force
}
Start-Transcript -LiteralPath (Join-Path $root 'flow.log') -NoClobber
try {
    Set-Stage 'verify_snapshot'
    $snapshot = Get-Content -LiteralPath (Join-Path $root 'snapshot.json') -Raw | ConvertFrom-Json
    if ($snapshot.profile -ne 'host_ethernet' -or
        (Get-FileHash -LiteralPath (Join-Path $package 'SHA256SUMS')).Hash.ToLower() -ne $snapshot.inventory_sha256) {
        throw 'Snapshot inventory/profile mismatch'
    }
    & py -3 (Join-Path $package 'scripts\verify_package.py')
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot verification failed' }
    Set-Stage 'prepare_ip'
    & (Join-Path $package 'scripts\create_profile.ps1') -Profile host_ethernet
    if ($Stage -eq 'synth') { Set-Stage 'synthesis_only' } else { Set-Stage 'synthesis_and_implementation' }
    & (Join-Path $package 'scripts\run.ps1') -Profile host_ethernet -Stage $Stage -RunRoot (Join-Path $root 'runs')
    if ($Stage -eq 'synth') {
        $record = Join-Path $package 'build\managed\host_ethernet\latest_synth.json'
        if (!(Test-Path -LiteralPath $record)) { throw 'Missing accepted synthesis record' }
        Set-Stage 'synthesis_passed_no_implementation' $record
    } else {
        $flows = @(Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Recurse -File -Filter completed_flow.json)
        if ($flows.Count -ne 1) { throw 'Missing or ambiguous completion record' }
        Set-Stage 'routed_needs_report_review' $flows[0].FullName
    }
} catch {
    Set-Stage 'failed' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally { Stop-Transcript }
