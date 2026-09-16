# Flow orchestration tests using real PowerShell and mocked Vivado/CIM only.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = Join-Path ([IO.Path]::GetTempPath()) ('ara full flow ' + [Guid]::NewGuid().ToString('N'))
$runner = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/run.ps1'
$fake = Join-Path $PSScriptRoot 'fake_vivado.ps1'
function Assert([bool]$Condition, [string]$Message) {
    if (!$Condition) { throw "ASSERT: $Message" }
}
function Get-CimInstance {
    param($ClassName, $Filter)
    if ($global:FakeCalls -eq 1) {
        # The lock must also stay held between the two native invocations.
        $locked = $false
        try {
            $h = [IO.File]::Open((Join-Path $global:FakePackage 'build/managed/run.lock'), 'Open', 'ReadWrite', 'None')
            $h.Dispose()
        } catch { $locked = $true }
        Assert $locked 'flow lock released between stages'
        if ($global:FakeCase -eq 'between_mutation') {
            Add-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv') -Value '// changed between stages'
        }
        if ($global:FakeCase -eq 'between_process') {
            [PSCustomObject]@{ ProcessId = 99; CreationDate = '2026-09-16'; CommandLine = 'leftover worker' }
        }
    }
}
foreach ($case in @('healthy', 'synth_error', 'impl_error', 'missing_marker', 'wrong_marker',
                    'mutated_input', 'between_mutation', 'between_process', 'held_lock', 'no_latest')) {
    $global:FakeCase = $case
    $global:FakePackage = Join-Path $base $case
    $global:FakeCalls = 0
    $global:FakeLog = @()
    $global:FakeSession = ''
    $global:FakeParent = ''
    foreach ($dir in @('scripts', 'rtl', 'build/managed', 'build/ara_dsa_vcu118')) {
        New-Item -ItemType Directory -Path (Join-Path $global:FakePackage $dir) | Out-Null
    }
    Copy-Item -LiteralPath $runner -Destination (Join-Path $global:FakePackage 'scripts/run.ps1')
    'module core; endmodule' | Set-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv')
    'test xpr' | Set-Content -LiteralPath (Join-Path $global:FakePackage 'build/ara_dsa_vcu118/ara_dsa_vcu118.xpr')
    $rows = foreach ($name in @('scripts/run.ps1', 'rtl/core.sv')) { ('0' * 64) + "  $name" }
    $rows | Set-Content -LiteralPath (Join-Path $global:FakePackage 'SHA256SUMS')
    $latest = Join-Path $global:FakePackage 'build/managed/latest_synth.json'
    $saved = '{"Run":"synth_abcdef012345","InputHash":"obsolete","Project":"old.xpr"}'
    if ($case -ne 'no_latest') { $saved | Set-Content -LiteralPath $latest }
    $lockPath = Join-Path $global:FakePackage 'build/managed/run.lock'
    $held = $null
    $before = (Get-Location).Path
    $caught = ''
    try {
        if ($case -eq 'held_lock') { $held = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
        try {
            & (Join-Path $global:FakePackage 'scripts/run.ps1') -Stage all -Vivado $fake -RunRoot (Join-Path $base 'runs')
        } catch { $caught = $_.ToString() }
    } finally { if ($null -ne $held) { $held.Dispose() } }
    $success = $case -in @('healthy', 'no_latest')
    Assert (($caught -eq '') -eq $success) "$case unexpected outcome: $caught"
    Assert ((Get-Location).Path -eq $before) 'location must be restored after success/failure'
    $h = [IO.File]::Open($lockPath, 'Open', 'ReadWrite', 'None')
    $h.Dispose()
    if ($case -eq 'held_lock') {
        Assert ($global:FakeCalls -eq 0) 'held lock must block all launches'
        Assert ($caught.Contains('Cannot acquire')) 'lock failure diagnostic'
    } else {
        $expected = 1
        if ($success -or $case -eq 'impl_error') { $expected = 2 }
        Assert ($global:FakeCalls -eq $expected) 'no local probe, retry, or implementation after failed synthesis'
        $synth = $global:FakeLog[0]
        Assert ($synth.Stage -eq 'synth' -and $synth.Parent -eq '-') 'always run fresh global synthesis'
        $flow = Split-Path -Parent $synth.Session
        Assert (Test-Path (Join-Path $flow 'project_before.xpr')) 'preserve original project evidence'
        $done = Join-Path $flow 'completed_flow.json'
        Assert ((Test-Path $done) -eq $success) 'no global success marker for partial/failed flow'
        $synthAccepted = $success -or $case -in @('impl_error', 'between_mutation', 'between_process')
        if ($synthAccepted) {
            $record = Get-Content -Raw -LiteralPath $latest | ConvertFrom-Json
            Assert ($record.Run -eq "synth_$($synth.Token)") 'latest synthesis must be this exact accepted result'
        } else {
            Assert ((Get-Content -Raw -LiteralPath $latest).Trim() -eq $saved) 'failed synthesis must preserve old record'
        }
        if ($expected -eq 2) {
            $impl = $global:FakeLog[1]
            Assert ($impl.Stage -eq 'impl' -and $impl.Parent -eq "synth_$($synth.Token)") 'implementation must use the new netlist'
            Assert ($impl.Session -ne $synth.Session) 'separate completion/log files for each stage'
        }
        if ($success) {
            $record = Get-Content -Raw -LiteralPath $done | ConvertFrom-Json
            Assert ($record.Runs.Count -eq 2 -and !$record.BitstreamGenerated) 'global evidence contains both stages; no bitstream claimed'
        }
    }
    Write-Host "PASS full flow $case"
}
Write-Host "Test evidence: $base"
