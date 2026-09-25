# Test double for audit_routed.ps1, not a Vivado emulator.
$global:FakeAuditCalls++
$i = [Array]::IndexOf($args, '-tclargs')
Assert ($i -ge 0 -and $args.Count -eq $i + 4) 'three exact Tcl arguments'
Assert ($args[[Array]::IndexOf($args, '-mode') + 1] -eq 'batch') 'noninteractive audit'
Assert ((Split-Path -Leaf $args[[Array]::IndexOf($args, '-source') + 1]) -eq 'audit_routed.tcl') 'only audit entry point'
$checkpoint = $args[$i + 1]
$global:FakeAuditSession = $args[$i + 2]
$token = $args[$i + 3]
Assert ($checkpoint -eq $global:FakeCheckpoint) 'exact old checkpoint, including spaces'
$reader = [IO.File]::Open($checkpoint, 'Open', 'Read', 'Read')
$reader.Dispose()
foreach ($path in @($checkpoint, (Join-Path $global:FakePackage 'build/managed/run.lock'))) {
    $denied = $false
    try { $writer = [IO.File]::Open($path, 'Open', 'ReadWrite', 'None'); $writer.Dispose() }
    catch { $denied = $true }
    Assert $denied 'checkpoint writes and concurrent managed runs must be blocked'
}
if ($global:FakeCase -eq 'mutated_script') {
    Add-Content -LiteralPath (Join-Path $global:FakePackage 'scripts/audit_support.tcl') -Value '# changed'
}
if ($global:FakeCase -ne 'missing_marker') {
    $name = "audit_$token"
    if ($global:FakeCase -eq 'wrong_marker') { $name = 'impl_old' }
    $name | Set-Content -LiteralPath (Join-Path $global:FakeAuditSession 'completed_audit.txt')
}
$reportDir = Join-Path $global:FakePackage "reports/audit_$token"
New-Item -ItemType Directory -Path $reportDir | Out-Null
foreach ($name in @('route_status', 'timing_summary', 'check_timing', 'cdc', 'drc',
                    'methodology', 'constraint_checks', 'boundary_checks', 'multiple_drivers')) {
    "fake $name" | Set-Content -LiteralPath (Join-Path $reportDir "$name.rpt")
}
$global:LASTEXITCODE = 0
if ($global:FakeCase -eq 'native_error') { $global:LASTEXITCODE = 1 }
