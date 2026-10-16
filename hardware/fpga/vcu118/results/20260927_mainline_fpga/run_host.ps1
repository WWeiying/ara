# Run from an isolated directory containing the exported package/ subdirectory.
# No programming, reset, firmware download, or changes to the user's Windows repo.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$package = Join-Path $root 'package'
$state = Join-Path $root 'state.json'
function Set-Stage([string]$Stage, [string]$Message = '') {
    $record = @{ Stage = $Stage; Updated = (Get-Date -Format o); Message = $Message;
                 Profile = 'host'; EthernetIntegrated = $false; BoardModified = $false }
    $temp = "$state.tmp"
    $record | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $state -Force
}
Start-Transcript -LiteralPath (Join-Path $root 'flow.log') -NoClobber
try {
    Set-Stage 'verify_snapshot'
    & py -3 (Join-Path $package 'scripts\verify_package.py')
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot verification failed' }
    Set-Stage 'prepare_ip'
    & (Join-Path $package 'scripts\create_profile.ps1') -Profile host
    Set-Stage 'synthesis_and_implementation'
    & (Join-Path $package 'scripts\run.ps1') -Profile host -Stage all -RunRoot (Join-Path $root 'runs')
    $flows = @(Get-ChildItem -LiteralPath (Join-Path $root 'runs') -Recurse -File -Filter completed_flow.json)
    if ($flows.Count -ne 1) { throw 'Missing or ambiguous completed_flow.json' }
    Set-Stage 'routed_needs_report_review' $flows[0].FullName
} catch {
    Set-Stage 'failed' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    Stop-Transcript
}
