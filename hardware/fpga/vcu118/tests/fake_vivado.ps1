# A test double for the external Vivado command, not an FPGA model.
$offset = [Array]::IndexOf($args, '-tclargs')
if ($offset -lt 0) { throw 'Missing Tcl arguments' }
$stage = $args[$offset + 1]
$session = $args[$offset + 2]
$token = $args[$offset + 3]
$parent = $args[$offset + 4]
$global:LASTEXITCODE = 0
$global:FakeCalls++
$global:FakeSession = $session
$global:FakeParent = $parent
if ($global:FakeCase -eq 'child_error') { $global:LASTEXITCODE = 1; return }
if ($global:FakeCase -eq 'mutated_input') {
    Add-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv') -Value '// changed'
}
if ($global:FakeCase -ne 'missing_marker') {
    "${stage}_$token" | Set-Content -LiteralPath (Join-Path $session 'completed_run.txt')
}
