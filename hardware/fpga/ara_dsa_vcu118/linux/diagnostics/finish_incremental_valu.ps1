#requires -Version 5.1
[CmdletBinding()]
param([int]$AuditProcessId = 0)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = 'D:\fpga_runs\ara_valu_release_20260930'
$package = 'D:\fpga_runs\ara_valu_fix_20260928\package'
$checkpoint = Join-Path $root 'ara_dsa_vcu118_routed.dcp'
$expected = 'E0C84074B6EBE8E3F510EE2E1556B5CD1F2DF90C87974430F31AE2CDCB397F76'
$out = Join-Path $root 'bitstream_host_ethernet'
function State([string]$stage, [string]$message = '') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      BoardModified=$false; AutomaticProgramming=$false; Profile='host_ethernet';
      HardwareValidated=$false; ManualCDCReviewComplete=$false} |
        ConvertTo-Json | Set-Content (Join-Path $root 'release_state.json') -Encoding UTF8
}
if (!(Test-Path $checkpoint) -or (Test-Path $out)) { throw 'Missing input or output already exists' }
Start-Transcript -LiteralPath (Join-Path $root 'release.log') -NoClobber
try {
    if ($AuditProcessId) {
        State 'waiting_for_audit'
        $process = Get-Process -Id $AuditProcessId -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            $command = (Get-CimInstance Win32_Process -Filter "ProcessId=$AuditProcessId").CommandLine
            if ($command -notlike '*-File *audit_routed.ps1*' -or $command -notlike "*$root*") {
                throw 'Audit PID does not identify the expected checkpoint audit'
            }
            Wait-Process -Id $AuditProcessId -Timeout 14400
        }
    }
    State 'checking_audit'
    if ((Get-FileHash $checkpoint).Hash -ne $expected) { throw 'Checkpoint hash mismatch' }
    $manifests = @(Get-ChildItem $root -Recurse -File -Filter completed_audit.json)
    if ($manifests.Count -ne 1) { throw 'Expected exactly one completed checkpoint audit' }
    $manifest = $manifests[0].FullName
    $audit = Get-Content $manifest -Raw | ConvertFrom-Json
    if ($audit.AutomatedChecksPassed -ne $true -or $audit.SHA256 -ne $expected -or
        $audit.Checkpoint -ne $checkpoint -or $audit.Profile -ne 'host_ethernet') {
        throw 'Audit does not match the expected routed design'
    }
    $summary = Get-Content (Join-Path $audit.Reports 'timing_summary.rpt') -Raw
    $match = [regex]::Match($summary, '(?m)^\s*WNS\(ns\)[^\r\n]*\r?\n[^\r\n]*\r?\n([^\r\n]+)')
    if (!$match.Success) { throw 'Missing complete timing summary' }
    $fields = $match.Groups[1].Value.Trim() -split '\s+'
    if ($fields.Count -ne 12) { throw 'Unexpected timing summary layout' }
    $culture = [Globalization.CultureInfo]::InvariantCulture
    foreach ($offset in @(0, 4, 8)) {
        $slack = [double]::Parse($fields[$offset], $culture)
        $total = [double]::Parse($fields[$offset+1], $culture)
        $failing = [long]::Parse($fields[$offset+2], $culture)
        $endpoints = [long]::Parse($fields[$offset+3], $culture)
        if ([double]::IsNaN($slack) -or [double]::IsInfinity($slack) -or
            $slack -lt 0 -or $total -ne 0 -or $failing -ne 0 -or $endpoints -le 0) {
            throw "Timing summary failed at column $offset"
        }
    }
    $drc = Get-Content (Join-Path $audit.Reports 'drc.rpt') -Raw
    if ($drc -match '(?im)^\s*\|\s*[^|]+\|\s*(Error|Critical Warning)\s*\|') {
        throw 'Blocking DRC finding; no bitstream requested'
    }
    # CDC findings remain visible. This produces a test artifact, not CDC signoff.
    State 'generating_bitstream' 'CDC/methodology review and board/Linux validation remain open'
    & (Join-Path $package 'scripts\write_profile_bit.ps1') -RunDir $root `
        -Profile host_ethernet -Out $out -AuditManifest $manifest
    if (!(Test-Path (Join-Path $out 'bitstream.json'))) { throw 'Missing bitstream completion manifest' }
    State 'bitstream_generated_not_board_validated' 'Native bitgen DRC retained; manual CDC review remains open'
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
} finally {
    Stop-Transcript
}
