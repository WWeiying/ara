#requires -Version 5.1
# Detached source rebuild through audited experimental bitgen. No board access.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Bundle,
      [string]$ResumeOptimized,
      [string]$OptimizedSHA256,
      [string]$ContinuationRoot,
      [string]$Vivado='D:\Xilinx\Vivado\2020.1\bin\vivado.bat')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Bundle=(Resolve-Path -LiteralPath $Bundle).Path
$package=Join-Path $Bundle 'package'
$policy=Get-Content (Join-Path $Bundle 'rebuild_inputs.json') -Raw | ConvertFrom-Json
$work=$Bundle
if ($ResumeOptimized) {
    if (!$ContinuationRoot -or $OptimizedSHA256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Resume requires a separate directory and optimized checkpoint hash'
    }
    $work=(Resolve-Path -LiteralPath $ContinuationRoot).Path
    if ($work -eq $Bundle) {throw 'Resume must preserve the original bundle'}
} elseif ($ContinuationRoot -or $OptimizedSHA256) {throw 'Incomplete resume arguments'}
$tools=$PSScriptRoot
$toolHashes=@{}
foreach ($name in @('rebuild_mainrtl.ps1','rebuild_mainrtl.tcl')) {
    $toolHashes[$name]=(Get-FileHash (Join-Path $tools $name)).Hash
}
$state=Join-Path $work 'state.json'
if (Test-Path $state) {throw 'Existing rebuild state; do not restart or overwrite'}
$oldProfile=$env:ARA_FPGA_PROFILE
$lock=$null
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      Profile='host_ethernet'; BoardModified=$false; HardwareValidated=$false;
      ManualCDCReviewComplete=$false; AutomaticProgramming=$false} |
        ConvertTo-Json | Set-Content "$state.tmp" -Encoding UTF8
    Move-Item "$state.tmp" $state -Force
}
function Verify-Inputs {
    foreach ($name in $toolHashes.Keys) {
        if ((Get-FileHash (Join-Path $tools $name)).Hash -ne $toolHashes[$name]) {throw 'Continuation tools changed'}
    }
    if ($ResumeOptimized -and (Get-FileHash $ResumeOptimized).Hash.ToLower() -ne $OptimizedSHA256) {
        throw 'Optimized checkpoint changed'
    }
    foreach ($entry in $policy.Files.PSObject.Properties) {
        if ((Get-FileHash (Join-Path $Bundle $entry.Name)).Hash.ToLower() -ne $entry.Value) {
            throw "Frozen input changed: $($entry.Name)"
        }
    }
    if ((Get-FileHash $policy.Reference).Hash.ToLower() -ne $policy.ReferenceSHA256) {
        throw 'Physical reference checkpoint changed'
    }
    & py -3 (Join-Path $package 'scripts\verify_package.py')
    if ($LASTEXITCODE -ne 0) {throw 'Package verification failed'}
}
function Run-Phase([string]$mode) {
    Verify-Inputs
    $lockPath=Join-Path $package 'build\managed\run.lock'
    New-Item -ItemType Directory -Force (Split-Path $lockPath) | Out-Null
    $script:lock=[IO.File]::Open($lockPath,'OpenOrCreate','ReadWrite','None')
    try {
        if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {
            throw 'Vivado is busy; no process killed'
        }
        State $mode
        Push-Location $runs
        try {
            $optimized='-'
            if ($ResumeOptimized) {$optimized=$ResumeOptimized}
            & $Vivado -mode batch -notrace -source (Join-Path $tools 'rebuild_mainrtl.tcl') `
                -log "$mode.log" -journal "$mode.jou" -tclargs $mode $package $runs $token "synth_$token" $policy.Reference $optimized
            if ($LASTEXITCODE -ne 0) {throw "$mode failed; inspect $runs\$mode.log"}
        } finally {Pop-Location}
    } finally {$script:lock.Dispose(); $script:lock=$null}
    Verify-Inputs
}
Start-Transcript -LiteralPath (Join-Path $work 'flow.log') -NoClobber
try {
    $env:ARA_FPGA_PROFILE='host_ethernet'
    State 'verify_snapshot'
    Verify-Inputs
    if ($ResumeOptimized) {
        @{Bundle=$Bundle; Optimized=$ResumeOptimized; SHA256=$OptimizedSHA256;
          ToolHashes=$toolHashes; Reference=$policy.Reference; ReferenceSHA256=$policy.ReferenceSHA256} |
            ConvertTo-Json -Depth 4 | Set-Content (Join-Path $work 'resume_inputs.json') -Encoding UTF8
        State 'recheck_synthesis_gate'
        & py -3 (Join-Path $Bundle 'check_rebuild_reports.py') synthesis `
            (Join-Path $Bundle 'runs\synthesis_timing.rpt') (Join-Path $Bundle 'baseline_synth.rpt') `
            --out (Join-Path $work 'synthesis_gate.json')
        if ($LASTEXITCODE -ne 0) {throw 'Original synthesis gate rejected'}
        $runs=Join-Path $work 'runs'
        New-Item -ItemType Directory $runs | Out-Null
        $token=[Guid]::NewGuid().ToString('N').Substring(0,12)
        Run-Phase resume
    } else {
    State 'prepare_ip'
    # Run in a child shell: a tool wrapper's exit must not terminate this supervisor.
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'scripts\create_profile.ps1') -Profile host_ethernet
    if ($LASTEXITCODE -ne 0) {throw 'IP/profile preparation failed'}
    $runs=Join-Path $Bundle 'runs'
    New-Item -ItemType Directory $runs | Out-Null
    $token=[Guid]::NewGuid().ToString('N').Substring(0,12)
    Run-Phase synth
    State 'synthesis_physical_review_gate'
    & py -3 (Join-Path $Bundle 'check_rebuild_reports.py') synthesis `
        (Join-Path $runs 'synthesis_timing.rpt') (Join-Path $Bundle 'baseline_synth.rpt') `
        --out (Join-Path $Bundle 'synthesis_gate.json')
    if ($LASTEXITCODE -ne 0) {throw 'Synthesis physical inventory changed or setup failed; no implementation'}
    Run-Phase impl
    }
    State 'audit_routed_checkpoint'
    $checkpoint=Join-Path $runs 'ara_dsa_vcu118_routed.dcp'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'scripts\audit_routed.ps1') `
        -Checkpoint $checkpoint -Profile host_ethernet -RunRoot (Join-Path $work 'audit')
    if ($LASTEXITCODE -ne 0) {throw 'Routed audit failed; bitgen not started'}
    Verify-Inputs
    $manifests=@(Get-ChildItem (Join-Path $work 'audit') -Recurse -Filter completed_audit.json)
    if ($manifests.Count -ne 1) {throw 'Missing/ambiguous completed audit'}
    $audit=Get-Content $manifests[0].FullName -Raw|ConvertFrom-Json
    if ($audit.AutomatedChecksPassed -ne $true -or $audit.Checkpoint -ne $checkpoint -or
        $audit.Profile -ne 'host_ethernet' -or $audit.SHA256 -ne (Get-FileHash $checkpoint).Hash) {
        throw 'Audit/checkpoint mismatch'
    }
    State 'release_report_gate'
    & py -3 (Join-Path $Bundle 'check_rebuild_reports.py') release $audit.Reports `
        (Join-Path $Bundle 'baseline_cdc.rpt') --out (Join-Path $work 'release_gate.json')
    if ($LASTEXITCODE -ne 0) {throw 'Release reports require review; no automatic bitgen'}
    State 'generating_experimental_bitstream' 'Known CDC findings remain open; not production signoff'
    $out=Join-Path $work 'bitstream_host_ethernet'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'scripts\write_profile_bit.ps1') `
        -RunDir $runs -Profile host_ethernet -Out $out -AuditManifest $manifests[0].FullName
    if ($LASTEXITCODE -ne 0 -or !(Test-Path (Join-Path $out 'bitstream.json'))) {
        throw 'Bitstream generation did not complete'
    }
    Verify-Inputs
    State 'bitstream_generated_not_programmed' 'Linux/board validation and manual CDC signoff remain open'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if ($null -ne $lock) {$lock.Dispose()}
    $env:ARA_FPGA_PROFILE=$oldProfile
    Stop-Transcript
}
