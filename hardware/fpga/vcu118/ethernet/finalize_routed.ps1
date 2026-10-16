#requires -Version 5.1
# New tool-only package, archived routed DCP, no board access or source rebuild.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SourcePackage,
      [Parameter(Mandatory=$true)][string]$Checkpoint,
      [Parameter(Mandatory=$true)][string]$SHA256,
      [Parameter(Mandatory=$true)][string]$BaselineCDC,
      [Parameter(Mandatory=$true)][string]$Out,
      [string]$Vivado='D:\Xilinx\Vivado\2020.1\bin\vivado.bat')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($SHA256 -notmatch '^[0-9a-fA-F]{64}$') {throw 'Invalid checkpoint hash'}
if (Test-Path -LiteralPath $Out) {throw 'Output already exists'}
if ((Get-FileHash -LiteralPath $Checkpoint).Hash -ne $SHA256) {throw 'Source checkpoint hash mismatch'}
if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {throw 'Vivado busy'}
New-Item -ItemType Directory $Out | Out-Null
$state=Join-Path $Out 'state.json'
$package=Join-Path $Out 'package'
$runs=Join-Path $Out 'runs'
$lock=$null
$inputHandle=$null
$oldProfile=$env:ARA_FPGA_PROFILE
function State([string]$stage,[string]$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$false;AutomaticProgramming=$false;HardwareValidated=$false;
      ManualCDCReviewComplete=$false;Profile='host_ethernet'} |
      ConvertTo-Json | Set-Content "$state.tmp" -Encoding UTF8
    Move-Item "$state.tmp" $state -Force
}
function Verify {
    foreach ($path in $hashes.Keys) {
        if ((Get-FileHash -LiteralPath $path).Hash -ne $hashes[$path]) {throw "Input changed: $path"}
    }
}
Start-Transcript -LiteralPath (Join-Path $Out 'flow.log') -NoClobber
try {
    State 'preparing_finalize'
    $env:ARA_FPGA_PROFILE='host_ethernet'
    $inputHandle=[IO.File]::Open($Checkpoint,'Open','Read','Read')
    if ((Get-FileHash $Checkpoint).Hash -ne $SHA256) {throw 'Checkpoint changed before lock'}
    New-Item -ItemType Directory $package | Out-Null
    # Only tooling is copied; checkpoint carries all RTL, placement and constraints.
    Copy-Item (Join-Path $SourcePackage 'scripts') $package -Recurse
    foreach ($name in @('common.tcl','audit_support.tcl','audit_routed.ps1','write_profile_bit.ps1','write_profile_bit.tcl')) {
        Copy-Item (Join-Path $PSScriptRoot "overlay\$name") (Join-Path $package "scripts\$name")
    }
    Copy-Item $BaselineCDC (Join-Path $Out 'baseline_cdc.rpt')
    Copy-Item (Join-Path $PSScriptRoot 'check_rebuild_reports.py') $Out
    Copy-Item (Join-Path $PSScriptRoot 'finalize_routed.tcl') $Out
    $hashes=@{}
    foreach ($file in @(Get-ChildItem $package -Recurse -File) + @(Get-ChildItem $PSScriptRoot -Recurse -File)) {
        $hashes[$file.FullName]=(Get-FileHash $file.FullName).Hash
    }
    foreach ($path in @($Checkpoint,$BaselineCDC,(Join-Path $Out 'baseline_cdc.rpt'),(Join-Path $Out 'check_rebuild_reports.py'),(Join-Path $Out 'finalize_routed.tcl'),(Join-Path $SourcePackage 'SHA256SUMS'))) {
        $hashes[$path]=(Get-FileHash $path).Hash
    }
    @{Checkpoint=$Checkpoint;SHA256=$SHA256;SourcePackage=$SourcePackage;Files=$hashes} |
        ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Out 'finalize_inputs.json') -Encoding UTF8
    $lockPath=Join-Path $SourcePackage 'build\managed\run.lock'
    $lock=[IO.File]::Open($lockPath,'OpenOrCreate','ReadWrite','None')
    try {
        Verify
        if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {throw 'Vivado busy'}
        State 'route_finalize'
        Push-Location $Out
        try {
            & $Vivado -mode batch -notrace -source (Join-Path $Out 'finalize_routed.tcl') -log finalize.log -journal finalize.jou -tclargs $package $Checkpoint $runs
            if ($LASTEXITCODE -ne 0) {throw 'Finalize failed; no retry or bitgen'}
        } finally {Pop-Location}
    } finally {$lock.Dispose();$lock=$null}
    Verify
    State 'fresh_checkpoint_audit'
    $newCheckpoint=Join-Path $runs 'ara_dsa_vcu118_routed.dcp'
    $hashes[$newCheckpoint]=(Get-FileHash $newCheckpoint).Hash
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'scripts\audit_routed.ps1') -Checkpoint $newCheckpoint -Profile host_ethernet -Vivado $Vivado -RunRoot (Join-Path $Out 'audit')
    if ($LASTEXITCODE -ne 0) {throw 'Fresh checkpoint audit failed'}
    Verify
    $manifests=@(Get-ChildItem (Join-Path $Out 'audit') -Recurse -Filter completed_audit.json)
    if ($manifests.Count -ne 1) {throw 'Missing or ambiguous audit'}
    $audit=Get-Content $manifests[0].FullName -Raw | ConvertFrom-Json
    if (!$audit.AutomatedChecksPassed -or $audit.Checkpoint -ne $newCheckpoint -or $audit.SHA256 -ne $hashes[$newCheckpoint] -or $audit.Profile -ne 'host_ethernet') {throw 'Audit binding failed'}
    State 'release_report_gate'
    & py -3 (Join-Path $Out 'check_rebuild_reports.py') release $audit.Reports (Join-Path $Out 'baseline_cdc.rpt') --out (Join-Path $Out 'release_gate.json')
    if ($LASTEXITCODE -ne 0) {throw 'Timing/CDC/report regression; bitgen blocked'}
    Verify
    State 'generating_experimental_bitstream' 'Known CDC findings remain; no production signoff'
    $bitOut=Join-Path $Out 'bitstream_host_ethernet'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'scripts\write_profile_bit.ps1') -RunDir $runs -Profile host_ethernet -Vivado $Vivado -Out $bitOut -AuditManifest $manifests[0].FullName
    if ($LASTEXITCODE -ne 0 -or !(Test-Path (Join-Path $bitOut 'bitstream.json'))) {throw 'Bitgen failed'}
    Verify
    State 'bitstream_generated_not_programmed' 'Board/Linux validation and manual CDC review remain open'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if ($null -ne $lock) {$lock.Dispose()}
    if ($null -ne $inputHandle) {$inputHandle.Dispose()}
    $env:ARA_FPGA_PROFILE=$oldProfile
    Stop-Transcript
}
