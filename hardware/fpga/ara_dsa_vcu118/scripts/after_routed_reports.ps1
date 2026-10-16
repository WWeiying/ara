# Wait for the exact reviewed route run; then attempt one post-route closure.
param(
    [int]$ParentProcessId=15180,
    [string]$Previous='D:\fpga_runs\ara_physical_netdelay_20260928_0832',
    [string]$Package='D:\fpga_runs\ara_singleid_synth_20260927_2011\package',
    [string]$Out='D:\fpga_runs\ara_postroute_close_20260928'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$log='D:\fpga_runs\ara_postroute_after_20260928.log'
if (Test-Path -LiteralPath $log) {throw 'Launcher log already exists'}
Start-Transcript -LiteralPath $log -NoClobber
try {
    $p=Get-Process -Id $ParentProcessId -ErrorAction SilentlyContinue
    if ($null -ne $p) {Wait-Process -Id $ParentProcessId}
    $state=Get-Content -LiteralPath (Join-Path $Previous 'state.json') -Raw | ConvertFrom-Json
    if ($state.Stage -ne 'failed' -or $state.ParentRun -ne 'synth_3aac2309e5ae' -or
        $state.BoardModified -ne $false) {throw 'Previous route did not stop at the reviewed gate'}
    $summary=Get-Content -LiteralPath (Join-Path $Previous 'reports\timing_summary.rpt') -Raw
    if ($summary -notmatch '(?m)^\s*-0\.014\s+-0\.094\s+16\s+912066\s+0\.010\s+0\.000\s+0\s+910911\s+0\.005\s+0\.000\s+0\s+306562') {
        throw 'Routed timing is not the reviewed 16-endpoint result'
    }
    $checkpoint=Join-Path $Previous 'impl_8b2e0aed7092\ara_dsa_vcu118_routed.dcp'
    if (!(Test-Path -LiteralPath $checkpoint)) {throw 'Missing reviewed routed checkpoint'}
    if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {
        throw 'Another Vivado process is active; no concurrent launch'
    }
    Write-Host "Starting one post-route optimization: $checkpoint"
    & (Join-Path $PSScriptRoot 'close_routed_setup.ps1') -Checkpoint $checkpoint `
        -Package $Package -Out $Out
    $closed=Get-Content -LiteralPath (Join-Path $Out 'state.json') -Raw | ConvertFrom-Json
    if ($closed.Stage -ne 'timing_passed_needs_full_audit') {
        throw "Post-route closure was not accepted: $($closed.Stage)"
    }
    Write-Host 'Routed timing passed; launching checkpoint-only audit.'
    & (Join-Path $Package 'scripts\audit_routed.ps1') `
        -Checkpoint (Join-Path $Out 'ara_dsa_vcu118_routed.dcp') `
        -Profile host_ethernet -RunRoot 'D:\fpga_runs'
    Write-Host 'Automated checkpoint audit finished; manual report review is still required before bitgen.'
} catch {
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    Stop-Transcript
}
