param([Parameter(Mandatory=$true)][int]$ReviewProcessId,
      [Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Review,
      [Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Start-Transcript -Path "$PSScriptRoot\continuation_queue.log" -NoClobber
try {
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$ReviewProcessId"
    if($null -ne $process) {
        if($process.CommandLine -notlike '*review_dual_physical.ps1*'){throw 'Review PID identity changed'}
        "Waiting for read-only review PID $ReviewProcessId"
        Wait-Process -Id $ReviewProcessId -ErrorAction SilentlyContinue
    }
    if(!(Test-Path "$Review\review_complete.txt")){throw 'Review did not complete; no implementation started'}
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\continue_dual_physical.ps1" -Bundle $Bundle -Review $Review -Out $Out
    if($LASTEXITCODE -ne 0){throw 'Physical trial stopped; inspect trial state'}
} finally {
    Stop-Transcript
}
