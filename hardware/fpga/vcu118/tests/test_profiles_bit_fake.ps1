$offset = [Array]::IndexOf($args, '-tclargs')
if ($offset -lt 0) { throw 'Missing Tcl arguments' }
$checkpoint = $args[$offset + 1]
$out = $args[$offset + 2]
if ($checkpoint -ne $global:ExpectedDcp) { throw 'Wrong routed DCP selected' }
if ($env:ARA_FPGA_PROFILE -ne 'host') { throw 'Wrong profile passed to Tcl' }
$global:FakeBitCalls++
$global:LASTEXITCODE = 0
if ($global:BitCase -eq 'child_error') { $global:LASTEXITCODE = 1; return }
if ($global:BitCase -eq 'missing_output') { return }
'fake bit' | Set-Content -LiteralPath (Join-Path $out 'ara_dsa_vcu118.bit')
'fake probes' | Set-Content -LiteralPath (Join-Path $out 'ara_dsa_vcu118.ltx')
