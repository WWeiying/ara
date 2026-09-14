# Run with Windows PowerShell 5.1 or pwsh. CIM and Vivado are test doubles.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = Join-Path ([IO.Path]::GetTempPath()) ('ara run test ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $base | Out-Null
$runner = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/run.ps1'
$fake = Join-Path $PSScriptRoot 'fake_vivado.ps1'
function Get-CimInstance {
    param($ClassName, $Filter)
    if ($global:FakeCase -eq 'existing_process') {
        [PSCustomObject]@{ ProcessId = 99; CreationDate = '2026-09-09'; CommandLine = 'task_worker.tcl' }
    }
}
function Assert([bool]$Condition, [string]$Message) {
    if (!$Condition) { throw "ASSERT: $Message" }
}
function Invoke-TestRun([string]$Stage = 'synth') {
    & (Join-Path $global:FakePackage 'scripts/run.ps1') -Vivado $fake -RunRoot (Join-Path $base 'runs') -Stage $Stage
}
foreach ($case in @('healthy', 'repeat_synth', 'inspect', 'inspect_stale', 'inspect_wrong_project', 'existing_process', 'held_lock', 'child_error', 'missing_marker', 'mutated_input', 'stale_input')) {
    $global:FakePackage = Join-Path $base $case
    $global:FakeCase = 'healthy'
    $global:FakeCalls = 0
    $global:FakeSession = ''
    $global:FakeParent = ''
    foreach ($dir in @('scripts', 'rtl', 'build/ara_dsa_vcu118')) {
        New-Item -ItemType Directory -Path (Join-Path $global:FakePackage $dir) | Out-Null
    }
    Copy-Item -LiteralPath $runner -Destination (Join-Path $global:FakePackage 'scripts/run.ps1')
    'module core; endmodule' | Set-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv')
    'test xpr' | Set-Content -LiteralPath (Join-Path $global:FakePackage 'build/ara_dsa_vcu118/ara_dsa_vcu118.xpr')
    $rows = foreach ($name in @('scripts/run.ps1', 'rtl/core.sv')) { ('0' * 64) + "  $name" }
    $rows | Set-Content -LiteralPath (Join-Path $global:FakePackage 'SHA256SUMS')
    Invoke-TestRun
    $latest = Join-Path $global:FakePackage 'build/managed/latest_synth.json'
    $saved = Get-Content -Raw -LiteralPath $latest
    $record = $saved | ConvertFrom-Json
    Assert ($global:FakeCalls -eq 1) 'healthy run must invoke child exactly once'
    $oldSession = $global:FakeSession
    $held = $null
    $global:FakeCase = $case
    try {
        if ($case -eq 'held_lock') {
            $held = [IO.File]::Open((Join-Path $global:FakePackage 'build/managed/run.lock'), 'Open', 'ReadWrite', 'None')
        }
        if ($case -in @('stale_input', 'inspect_stale')) {
            Add-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv') -Value '// new revision'
        }
        if ($case -eq 'inspect_wrong_project') {
            $record.Project = 'different.xpr'
            $record | ConvertTo-Json | Set-Content -LiteralPath $latest
            $saved = Get-Content -Raw -LiteralPath $latest
        }
        $caught = ''
        try {
            if ($case -in @('healthy', 'stale_input')) { Invoke-TestRun impl }
            elseif ($case -in @('inspect', 'inspect_stale', 'inspect_wrong_project')) { Invoke-TestRun inspect }
            else { Invoke-TestRun }
        } catch { $caught = $_.ToString() }
        if ($case -in @('healthy', 'repeat_synth', 'inspect', 'inspect_stale')) {
            Assert (!$caught) "implementation failed: $caught"
            if ($case -eq 'healthy') {
                Assert ($global:FakeParent -eq $record.Run) 'implementation must use recorded parent'
            }
            Assert ($global:FakeSession -ne $oldSession) 'run directories must differ'
            if ($case -in @('inspect', 'inspect_stale')) {
                Assert ($global:FakeParent -eq $record.Run) 'inspect must use the recorded OLD netlist'
                $inspected = Get-Content -Raw (Join-Path $global:FakeSession 'inspected_synth.json') | ConvertFrom-Json
                Assert ($inspected.InputHash -eq $record.InputHash) 'preserve inspected input provenance'
                $inspectionRun = (Get-Content -Raw (Join-Path $global:FakeSession 'completed_run.txt')).Trim()
                $provenance = Get-Content -Raw (Join-Path $global:FakePackage "reports/$inspectionRun/inspection.json") | ConvertFrom-Json
                Assert ($provenance.InspectedSynthesis.InputHash -eq $record.InputHash) 'reports carry original synthesis fingerprint'
                Assert (($provenance.CurrentInputHash -ne $record.InputHash) -eq ($case -eq 'inspect_stale')) 'distinguish changed inputs from inspected netlist'
            }
        } else {
            $expected = @{
                existing_process = 'Vivado processes already exist'
                held_lock = 'Cannot acquire'
                child_error = 'Vivado failed'
                missing_marker = 'completed_run.txt'
                mutated_input = 'Inputs changed during the run'
                stale_input = 'Inputs/project changed'
                inspect_wrong_project = 'Inputs/project changed'
            }
            Assert ($caught.Contains($expected[$case])) "$case returned the wrong error: $caught"
        }
        $updated = Get-Content -Raw -LiteralPath $latest
        if ($case -eq 'repeat_synth') {
            Assert (($updated | ConvertFrom-Json).Run -ne $record.Run) 'successful retry must update the synthesis record'
        } else {
            Assert ($updated -eq $saved) 'do not overwrite synthesis record on failure/implementation'
        }
        Assert (Test-Path (Join-Path $oldSession 'completed_run.txt')) 'old completed work must survive'
        if ($case -in @('existing_process', 'held_lock', 'stale_input', 'inspect_wrong_project')) {
            Assert ($global:FakeCalls -eq 1) 'preflight must not launch Vivado'
        }
    } finally { if ($null -ne $held) { $held.Dispose() } }
    # A failed invocation must release its own handle, without deleting the lock.
    $probe = [IO.File]::Open((Join-Path $global:FakePackage 'build/managed/run.lock'), 'Open', 'ReadWrite', 'None')
    $probe.Dispose()
    Write-Host "PASS $case"
}
Write-Host "Test evidence: $base"
