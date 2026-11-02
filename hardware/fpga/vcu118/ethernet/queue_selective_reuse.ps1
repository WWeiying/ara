# One successor only. Preserve the producer's checkpoint and reports first.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$config = Get-Content (Join-Path $root 'release_inputs.json') -Raw | ConvertFrom-Json
$deadline = (Get-Date).AddHours(4)
function Queue-State([string]$stage) {
    @{Stage=$stage;Updated=(Get-Date -Format o);ProcessId=$PID;BoardModified=$false} |
        ConvertTo-Json | Set-Content (Join-Path $root 'queue_state.json') -Encoding UTF8
}
try {
    Queue-State 'waiting_for_previous_failure_reports'
    do {
        $previous = Get-Content (Join-Path $config.PreviousRoot 'state.json') -Raw | ConvertFrom-Json
        if ($previous.Stage -eq 'stopped_for_review') {break}
        if ($previous.Stage -eq 'bitstream_generated') {throw 'Previous build succeeded; no recovery required'}
        if ((Get-Date) -gt $deadline) {throw 'Previous reports did not complete; do not interrupt producer'}
        Start-Sleep -Seconds 60
    } while ($true)
    $log = Join-Path $config.PreviousRoot 'impl\impl_existing.log'
    if (!(Select-String -LiteralPath $log -SimpleMatch '466 signals failed to route due to routing congestion' -Quiet)) {
        throw 'Previous failure differs from reviewed congestion evidence'
    }
    # The old supervisor updates state before its finally block releases locks.
    Start-Sleep -Seconds 10
    if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Another Vivado is running'}
    Queue-State 'starting_selective_physical_recovery'
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $root 'run_release.ps1')
    if ($LASTEXITCODE) {throw 'Recovery stopped; preserve state.json and reports for review'}
    Queue-State 'completed'
} catch {
    @{Stage='stopped_for_review';Message=($_ | Out-String);Updated=(Get-Date -Format o);ProcessId=$PID} |
        ConvertTo-Json | Set-Content (Join-Path $root 'queue_state.json') -Encoding UTF8
    exit 1
}
