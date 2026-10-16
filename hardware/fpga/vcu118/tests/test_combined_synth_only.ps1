# Mock-only: no Vivado, synthesis, implementation or board access.
$ErrorActionPreference = 'Stop'
$runner = Join-Path (Split-Path $PSScriptRoot -Parent) 'ethernet/run_combined.ps1'
$base = Join-Path ([IO.Path]::GetTempPath()) ('combined_gate_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $base | Out-Null
try {
    foreach ($case in @('default', 'explicit', 'dual', 'rejected')) {
        $root = Join-Path $base $case
        $package = Join-Path $root 'package'
        $scripts = Join-Path $package 'scripts'
        New-Item -ItemType Directory -Path $scripts -Force | Out-Null
        Copy-Item -LiteralPath $runner -Destination (Join-Path $root 'run_combined.ps1')
        'fixture' | Set-Content (Join-Path $package 'SHA256SUMS')
        $profile = if ($case -eq 'dual') { 'dual_ddr_ethernet' } else { 'host_ethernet' }
        @{profile=$profile; inventory_sha256=(Get-FileHash (Join-Path $package 'SHA256SUMS')).Hash.ToLower()} |
            ConvertTo-Json | Set-Content (Join-Path $root 'snapshot.json')
        '# mock' | Set-Content (Join-Path $scripts 'create_profile.ps1')
        @'
param($Profile, $Stage, $RunRoot)
if ($Stage -ne 'synth') { throw 'IMPLEMENTATION WAS REQUESTED' }
$package = Split-Path $PSScriptRoot -Parent
$root = Split-Path $package -Parent
$Stage | Set-Content (Join-Path $root 'requested_stage.txt')
if (Test-Path (Join-Path $root 'reject')) { throw 'Synthesis hold/skew gate failed' }
$record = Join-Path $package "build/managed/$Profile"
New-Item -ItemType Directory -Path $record -Force | Out-Null
'{}' | Set-Content (Join-Path $record 'latest_synth.json')
'@ | Set-Content (Join-Path $scripts 'run.ps1')
        @'
function global:py { $global:LASTEXITCODE = 0 }
if ($args.Count) { & "$PSScriptRoot/run_combined.ps1" -Stage synth }
else { & "$PSScriptRoot/run_combined.ps1" }
exit $LASTEXITCODE
'@ | Set-Content (Join-Path $root 'invoke.ps1')
        if ($case -eq 'rejected') { 'reject' | Set-Content (Join-Path $root 'reject') }
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $root 'invoke.ps1'))
        if ($case -eq 'explicit') { $arguments += 'explicit' }
        & powershell.exe @arguments | Out-Null
        $exitCode = $LASTEXITCODE
        $state = Get-Content (Join-Path $root 'state.json') -Raw | ConvertFrom-Json
        if ((Get-Content (Join-Path $root 'requested_stage.txt')).Trim() -ne 'synth' -or $state.BoardModified) {
            throw "Unsafe stage/board state in $case"
        }
        if ($case -eq 'rejected') {
            if ($exitCode -eq 0 -or $state.Stage -ne 'failed') { throw 'Failed gate accepted' }
        } elseif ($exitCode -ne 0 -or $state.Stage -ne 'synthesis_passed_no_implementation' -or $state.Profile -ne $profile) {
            throw "Missing synthesis-only completion in $case"
        }
        Write-Output "PASS $case"
    }
} finally { Remove-Item -LiteralPath $base -Recurse -Force }
