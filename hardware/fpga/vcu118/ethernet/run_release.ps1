# Complete experimental release flow, run from a frozen independent bundle.
# Physical/CDC gates remain strict; no flash programming or automatic retries.
param([switch]$ValidateBoard)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$package = Join-Path $root 'package'
$config = Get-Content (Join-Path $root 'release_inputs.json') -Raw | ConvertFrom-Json
$vivado = 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
$env:ARA_FPGA_PROFILE = 'dual_ddr_ethernet'
$modified = $false
$lock = $null
function State([string]$stage, [string]$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      SourceCommit=$config.SourceCommit;Profile='dual_ddr_ethernet';BoardModified=$script:modified;
      FlashModified=$false;ManualCDCSignoff=$false} | ConvertTo-Json |
        Set-Content (Join-Path $root 'state.json.tmp') -Encoding UTF8
    Move-Item (Join-Path $root 'state.json.tmp') (Join-Path $root 'state.json') -Force
}
function Verify-Inputs {
    foreach ($row in $config.Files) {
        if ((Get-FileHash -LiteralPath $row.Path).Hash.ToLower() -ne $row.SHA256) {
            throw "Frozen release input changed: $($row.Path)"
        }
    }
    & py -3 (Join-Path $package 'scripts\verify_package.py')
    if ($LASTEXITCODE) {throw 'Frozen package verification failed'}
}
function Run-Tool([string]$mode, [string]$directory) {
    if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
    Push-Location $directory
    try {
        & $vivado -mode batch -notrace -nojournal -log (Join-Path $directory 'vivado.log') `
            -source (Join-Path $package 'ethernet\release_build.tcl') `
            -tclargs $mode $package $directory $config.Token $config.Reference (Join-Path $root 'tools')
        if ($LASTEXITCODE) {throw "$mode failed; inspect $directory\vivado.log"}
    } finally {Pop-Location}
}
if (Test-Path (Join-Path $root 'state.json')) {throw 'Existing release state; inspect rather than restart'}
Start-Transcript -LiteralPath (Join-Path $root 'release.log') -NoClobber
try {
    foreach ($directory in @('synth','impl','audit')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $root $directory) | Out-Null
    }
    State 'verify_frozen_release'
    Verify-Inputs
    if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
    State 'prepare_ip_and_project'
    & (Join-Path $package 'scripts\create_profile.ps1') -Profile dual_ddr_ethernet
    if ($LASTEXITCODE) {throw 'Project/IP preparation failed'}
    New-Item -ItemType Directory -Force -Path (Join-Path $package 'build\managed') | Out-Null
    $lock=[IO.File]::Open((Join-Path $package 'build\managed\run.lock'),'OpenOrCreate','ReadWrite','None')
    State 'synthesis'
    Run-Tool 'synth' (Join-Path $root 'synth')
    State 'synthesis_setup_and_reviewed_physical_gate'
    & py -3 (Join-Path $package 'ethernet\check_rebuild_reports.py') synthesis `
        (Join-Path $root 'synth\synthesis_timing.rpt') $config.BaselineSynthesis `
        --out (Join-Path $root 'synthesis_gate.json')
    if ($LASTEXITCODE) {throw 'New synthesis violation; implementation not launched'}
    Verify-Inputs
    State 'implementation_using_closed_reference'
    Run-Tool 'impl' (Join-Path $root 'impl')
    $checkpoint=Join-Path $root 'impl\ara_dsa_vcu118_routed.dcp'
    $lock.Dispose(); $lock=$null
    State 'routed_drc_cdc_timing_audit'
    & (Join-Path $package 'scripts\audit_routed.ps1') -Checkpoint $checkpoint `
        -Profile dual_ddr_ethernet -RunRoot (Join-Path $root 'audit')
    if ($LASTEXITCODE) {throw 'Routed audit failed'}
    $audits=@(Get-ChildItem (Join-Path $root 'audit') -Recurse -File -Filter completed_audit.json)
    if ($audits.Count -ne 1) {throw 'Missing/ambiguous routed audit'}
    $audit=Get-Content $audits[0].FullName -Raw | ConvertFrom-Json
    State 'review_new_cdc_rows_and_release_gates'
    & py -3 (Join-Path $package 'ethernet\check_rebuild_reports.py') release `
        $audit.Reports $config.BaselineCDC --out (Join-Path $root 'release_gate.json')
    if ($LASTEXITCODE) {throw 'Release gate failed; no bitstream or board programming'}
    Verify-Inputs
    State 'generate_bitstream'
    & (Join-Path $package 'scripts\write_profile_bit.ps1') -RunDir (Join-Path $root 'impl') `
        -Profile dual_ddr_ethernet -AuditManifest $audits[0].FullName -Out (Join-Path $root 'bitstream')
    if ($LASTEXITCODE) {throw 'Bitstream generation failed'}
    $artifacts=@{}
    foreach ($extension in @('bit','ltx')) {
        $path=Join-Path $root "bitstream\ara_dsa_vcu118.$extension"
        $artifacts[$path]=(Get-FileHash -LiteralPath $path).Hash
    }
    $artifacts | ConvertTo-Json | Set-Content (Join-Path $root 'artifacts.json') -Encoding UTF8
    State 'bitstream_generated'
    if ($ValidateBoard) {
        Verify-Inputs
        $modified=$true
        State 'board_smoke_validation'
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $root 'board\run_board.ps1')
        if ($LASTEXITCODE) {throw 'Board smoke failed; board preserved for diagnosis'}
        State 'linux_boot_and_system_validation'
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $root 'linux\run_linux.ps1')
        if ($LASTEXITCODE) {throw 'Linux validation failed; preserve UART and board state'}
        State 'linux_boot_and_basic_tests_passed' 'Experimental image; not exhaustive RVV or full-capacity DDR validation'
    }
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if ($null -ne $lock) {$lock.Dispose()}
    Stop-Transcript
}
