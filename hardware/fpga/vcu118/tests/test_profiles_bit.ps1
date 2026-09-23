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
        $caught = ''
        try { & $runner -RunDir $run -Profile host -Vivado $fake }
        catch { $caught = $_.ToString() }
        Assert ($caught.Contains('already exists')) 'existing outputs cannot be overwritten'
    }
    Write-Host "PASS bit selection $case"
}
Write-Host "Test evidence: $base"
