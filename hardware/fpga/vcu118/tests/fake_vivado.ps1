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
$global:FakeLog += [PSCustomObject]@{ Stage = $stage; Session = $session; Token = $token; Parent = $parent }
$locked = $false
try {
    $probe = [IO.File]::Open((Join-Path $global:FakePackage 'build/managed/run.lock'), 'Open', 'ReadWrite', 'None')
    $probe.Dispose()
} catch { $locked = $true }
if (!$locked) { throw 'Managed flow lock was not held during Vivado execution' }
if ($global:FakeCase -eq 'child_error') { $global:LASTEXITCODE = 1; return }
if (($global:FakeCase -eq 'synth_error' -and $stage -eq 'synth') -or
    ($global:FakeCase -eq 'impl_error' -and $stage -eq 'impl')) {
    $global:LASTEXITCODE = 1; return
}
if ($global:FakeCase -eq 'mutated_input') {
    Add-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv') -Value '// changed'
}
if ($global:FakeCase -ne 'missing_marker') {
    $marker = "${stage}_$token"
    if ($global:FakeCase -eq 'wrong_marker') { $marker = 'synth_abcdef012345' }
    $marker | Set-Content -LiteralPath (Join-Path $session 'completed_run.txt')
}
