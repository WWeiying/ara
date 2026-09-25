Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = Join-Path ([IO.Path]::GetTempPath()) ('ara bit profiles ' + [Guid]::NewGuid().ToString('N'))
$scripts = Join-Path $base 'scripts'
New-Item -ItemType Directory -Path $scripts | Out-Null
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/write_profile_bit.ps1'
$runner = Join-Path $scripts 'write_profile_bit.ps1'
Copy-Item -LiteralPath $source -Destination $runner
$fake = Join-Path $PSScriptRoot 'test_profiles_bit_fake.ps1'
$global:FakeBitCalls = 0
$global:ExpectedBitMode = 'full'
function Get-CimInstance { param($ClassName, $Filter) }
function Assert([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message } }
$env:ARA_FPGA_PROFILE = 'prior'
foreach ($case in @('nested', 'flat', 'missing', 'duplicate', 'wrong_profile', 'child_error', 'missing_output')) {
    $global:BitCase = $case
    $run = Join-Path $base $case
    New-Item -ItemType Directory -Path $run | Out-Null
    $dcpDir = Join-Path $run 'impl_test'
    if ($case -eq 'nested') { $dcpDir = Join-Path $run 'impl/impl_test' }
    New-Item -ItemType Directory -Path $dcpDir | Out-Null
    $global:ExpectedDcp = Join-Path $dcpDir 'ara_dsa_vcu118_routed.dcp'
    if ($case -ne 'missing') { 'checkpoint' | Set-Content -LiteralPath $global:ExpectedDcp }
    if ($case -eq 'duplicate') {
        'checkpoint2' | Set-Content -LiteralPath (Join-Path $dcpDir 'other_routed.dcp')
    }
    if ($case -eq 'wrong_profile') {
        '{"Profile":"baseline"}' | Set-Content -LiteralPath (Join-Path $run 'completed_flow.json')
    }
    $caught = ''; $before = $global:FakeBitCalls; $location = (Get-Location).Path
    try { & $runner -RunDir $run -Profile host -Vivado $fake }
    catch { $caught = $_.ToString() }
    $success = $case -in @('nested', 'flat')
    Assert (($caught -eq '') -eq $success) "$case unexpected result: $caught"
    Assert ($env:ARA_FPGA_PROFILE -eq 'prior') 'restore caller environment'
    Assert ((Get-Location).Path -eq $location) 'restore caller directory'
    $out = Join-Path $run 'bitstream_host'
    Assert ((Test-Path (Join-Path $out 'bitstream.json')) -eq $success) 'no false success artifact'
    if ($case -in @('missing', 'duplicate', 'wrong_profile')) {
        Assert ($global:FakeBitCalls -eq $before) 'invalid selection must not launch Vivado'
    }
    if ($success) {
        $record = Get-Content -Raw -LiteralPath (Join-Path $out 'bitstream.json') | ConvertFrom-Json
        Assert ($record.Checkpoint -eq $global:ExpectedDcp) 'exact routed DCP recorded'
        Assert ($record.Profile -eq 'host' -and $record.Outputs.Count -eq 2) 'provenance and hashes saved'
        Assert ($record.ReportMode -eq 'full') 'default full reports retained'
        $caught = ''
        try { & $runner -RunDir $run -Profile host -Vivado $fake }
        catch { $caught = $_.ToString() }
        Assert ($caught.Contains('already exists')) 'existing outputs cannot be overwritten'
    }
    Write-Host "PASS bit selection $case"
}
foreach ($name in @('audit_routed.ps1', 'audit_routed.tcl', 'audit_support.tcl',
                    'common.tcl', 'config.tcl', 'constraint_checks.tcl', 'warning_details.tcl')) {
    Copy-Item -LiteralPath (Join-Path (Split-Path $source -Parent) $name) -Destination $scripts
}
$run = Join-Path $base 'audited'
$dcpDir = Join-Path $run 'impl'
$auditDir = Join-Path $run 'audit'
$reports = Join-Path $auditDir 'reports/audit_test'
New-Item -ItemType Directory -Path $dcpDir, $reports | Out-Null
$global:ExpectedDcp = Join-Path $dcpDir 'ara_dsa_vcu118_routed.dcp'
'checkpoint' | Set-Content -LiteralPath $global:ExpectedDcp
'audit_test' | Set-Content -LiteralPath (Join-Path $auditDir 'completed_audit.txt')
$scriptHashes = @{}
foreach ($name in @('audit_routed.ps1', 'audit_routed.tcl', 'audit_support.tcl',
                    'common.tcl', 'config.tcl', 'constraint_checks.tcl', 'warning_details.tcl')) {
    $scriptHashes[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $scripts $name)).Hash
}
$reportHashes = @{}
foreach ($name in @('route_status', 'timing_summary', 'check_timing', 'cdc', 'drc',
                    'methodology', 'constraint_checks', 'boundary_checks', 'multiple_drivers')) {
    $file = Join-Path $reports "$name.rpt"
    "fake $name" | Set-Content -LiteralPath $file
    $reportHashes["$name.rpt"] = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash
}
$manifest = Join-Path $auditDir 'completed_audit.json'
@{ Mode = 'routed checkpoint only'; Profile = 'host'; Checkpoint = $global:ExpectedDcp;
   SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $global:ExpectedDcp).Hash;
   Length = (Get-Item -LiteralPath $global:ExpectedDcp).Length; Audit = 'audit_test';
   Reports = $reports; Directory = $auditDir; AutomatedChecksPassed = $true;
   ScriptHashes = $scriptHashes; ReportHashes = $reportHashes } | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $manifest
$global:ExpectedBitMode = 'audited'
foreach ($case in @('valid', 'report_changed', 'script_changed', 'checkpoint_changed', 'profile_changed')) {
    $audit = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if ($case -eq 'report_changed') { 'tampered' | Set-Content -LiteralPath (Join-Path $reports 'cdc.rpt') }
    if ($case -eq 'script_changed') { Add-Content -LiteralPath (Join-Path $scripts 'audit_support.tcl') -Value 'tampered' }
    if ($case -eq 'checkpoint_changed') { 'tampered' | Set-Content -LiteralPath $global:ExpectedDcp }
    if ($case -eq 'profile_changed') { $audit.Profile = 'baseline'; $audit | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifest }
    $before = $global:FakeBitCalls
    $out = Join-Path $run "bitstream_$case"
    $caught = ''
    try { & $runner -RunDir $run -Profile host -AuditManifest $manifest -Out $out -Vivado $fake }
    catch { $caught = $_.ToString() }
    Assert (($caught -eq '') -eq ($case -eq 'valid')) "$case audited result: $caught"
    Assert ((Test-Path -LiteralPath (Join-Path $out 'bitstream.json')) -eq ($case -eq 'valid')) 'no false audited success'
    if ($case -ne 'valid') { Assert ($global:FakeBitCalls -eq $before) 'reject stale audit before Vivado' }
    if ($case -eq 'valid') {
        $record = Get-Content -LiteralPath (Join-Path $out 'bitstream.json') -Raw | ConvertFrom-Json
        Assert ($record.ReportMode -eq 'audited' -and $record.AuditManifestSHA256 -ne '') 'audited provenance'
    }
    if ($case -eq 'report_changed') { 'fake cdc' | Set-Content -LiteralPath (Join-Path $reports 'cdc.rpt') }
    if ($case -eq 'script_changed') { Copy-Item -LiteralPath (Join-Path (Split-Path $source -Parent) 'audit_support.tcl') -Destination $scripts -Force }
    if ($case -eq 'checkpoint_changed') { 'checkpoint' | Set-Content -LiteralPath $global:ExpectedDcp }
    if ($case -eq 'profile_changed') { $audit.Profile = 'host'; $audit | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifest }
    Write-Host "PASS audited bit selection $case"
}
Write-Host "Test evidence: $base"
