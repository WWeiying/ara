# Real PowerShell orchestration; only Vivado/CIM are mocked. No XPR is provided.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = Join-Path ([IO.Path]::GetTempPath()) ('ara checkpoint audit ' + [Guid]::NewGuid().ToString('N'))
$scripts = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts'
$fake = Join-Path $PSScriptRoot 'fake_audit_vivado.ps1'
function Assert([bool]$Condition, [string]$Message) { if (!$Condition) { throw "ASSERT: $Message" } }
function Get-CimInstance {
    param($ClassName, $Filter)
    if ($global:FakeCase -eq 'existing_vivado') { [PSCustomObject]@{ ProcessId = 99 } }
}
foreach ($case in @('healthy', 'native_error', 'missing_marker', 'wrong_marker', 'mutated_script',
                    'held_lock', 'existing_vivado', 'missing_dcp', 'empty_dcp', 'wrong_extension', 'no_argument')) {
    $global:FakeCase = $case
    $global:FakePackage = Join-Path $base $case
    $global:FakeAuditCalls = 0
    $global:FakeAuditSession = ''
    foreach ($dir in @('scripts', 'build/managed', 'old run')) {
        New-Item -ItemType Directory -Path (Join-Path $global:FakePackage $dir) | Out-Null
    }
    foreach ($name in @('audit_routed.ps1', 'audit_routed.tcl', 'audit_support.tcl',
                       'common.tcl', 'config.tcl', 'constraint_checks.tcl', 'warning_details.tcl')) {
        Copy-Item -LiteralPath (Join-Path $scripts $name) -Destination (Join-Path $global:FakePackage 'scripts')
    }
    $global:FakeCheckpoint = Join-Path $global:FakePackage 'old run/old_routed.dcp'
    'old checkpoint' | Set-Content -LiteralPath $global:FakeCheckpoint
    if ($case -eq 'missing_dcp') { Remove-Item -LiteralPath $global:FakeCheckpoint }
    if ($case -eq 'empty_dcp') { [IO.File]::WriteAllText($global:FakeCheckpoint, '') }
    if ($case -eq 'wrong_extension') {
        Move-Item -LiteralPath $global:FakeCheckpoint -Destination "$global:FakeCheckpoint.txt"
        $global:FakeCheckpoint += '.txt'
    }
    $latest = Join-Path $global:FakePackage 'build/managed/latest_synth.json'
    'old synth record' | Set-Content -LiteralPath $latest
    $lockPath = Join-Path $global:FakePackage 'build/managed/run.lock'
    $held = $null
    $before = (Get-Location).Path
    $caught = ''
    try {
        if ($case -eq 'held_lock') { $held = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
        try {
            $checkpointArg = $global:FakeCheckpoint
            if ($case -eq 'no_argument') { $checkpointArg = '' }
            & (Join-Path $global:FakePackage 'scripts/audit_routed.ps1') $checkpointArg -Vivado $fake -RunRoot (Join-Path $base 'runs')
        } catch { $caught = $_.ToString() }
    } finally { if ($null -ne $held) { $held.Dispose() } }
    $success = $case -eq 'healthy'
    Assert (($caught -eq '') -eq $success) "$case unexpected result: $caught"
    Assert ((Get-Location).Path -eq $before) 'restore caller location'
    Assert ((Get-Content -Raw -LiteralPath $latest).Trim() -eq 'old synth record') 'preserve old synthesis record'
    Assert (!(Test-Path -LiteralPath (Join-Path $global:FakePackage 'old run/completed_flow.json'))) 'do not rewrite old flow outcome'
    if ($case -notin @('missing_dcp', 'empty_dcp')) {
        Assert ((Get-Content -Raw -LiteralPath $global:FakeCheckpoint).Trim() -eq 'old checkpoint') 'preserve checkpoint contents'
        $h = [IO.File]::Open($global:FakeCheckpoint, 'Open', 'ReadWrite', 'None'); $h.Dispose()
    }
    if (Test-Path -LiteralPath $lockPath) {
        $h = [IO.File]::Open($lockPath, 'Open', 'ReadWrite', 'None'); $h.Dispose()
    }
    $launch = $case -in @('healthy', 'native_error', 'missing_marker', 'wrong_marker', 'mutated_script')
    Assert ($global:FakeAuditCalls -eq [int]$launch) 'exactly one audit, no retry/build'
    if ($launch) {
        $done = Join-Path $global:FakeAuditSession 'completed_audit.json'
        Assert ((Test-Path -LiteralPath $done) -eq $success) 'no accepted marker on native/script errors'
        Assert (!(Test-Path -LiteralPath (Join-Path $global:FakeAuditSession 'completed_flow.json'))) 'audit is not a full build'
        if ($success) {
            $record = Get-Content -Raw -LiteralPath $done | ConvertFrom-Json
            Assert ($record.Checkpoint -eq $global:FakeCheckpoint) 'checkpoint provenance'
            Assert ($record.SHA256 -eq (Get-FileHash -Algorithm SHA256 -LiteralPath $global:FakeCheckpoint).Hash) 'checkpoint hash'
            Assert ($record.ScriptHashes.'audit_routed.ps1' -ne '') 'script provenance'
            Assert ($record.ScriptHashes.'warning_details.tcl' -ne '') 'warning-query provenance'
            Assert ($record.AutomatedChecksPassed -and $record.ManualReviewRequired -and !$record.BitstreamGenerated) 'bounded success statement'
        }
    }
    Write-Host "PASS checkpoint wrapper $case"
}
Write-Host "Test evidence: $base"
