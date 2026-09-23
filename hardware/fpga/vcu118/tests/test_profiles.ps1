# Real PowerShell execution with mocked native Vivado and CIM. No FPGA model.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = Join-Path ([IO.Path]::GetTempPath()) ('ara profiles ' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts'
$global:FakePackage = Join-Path $base 'package'
$global:FakeCase = 'healthy'
$global:FakeCalls = 0
$global:FakeLog = @()
$global:FakeSession = ''
$global:FakeParent = ''
$global:ExpectedProfile = 'baseline'
$global:ObservedProfiles = @()
function Assert([bool]$Condition, [string]$Message) {
    if (!$Condition) { throw "ASSERT: $Message" }
}
function Get-CimInstance {
    param($ClassName, $Filter)
    Assert ($env:ARA_FPGA_PROFILE -eq $global:ExpectedProfile) 'selected profile propagated'
    $global:ObservedProfiles += $env:ARA_FPGA_PROFILE
}
foreach ($dir in @('scripts', 'rtl', 'build/managed')) {
    New-Item -ItemType Directory -Path (Join-Path $global:FakePackage $dir) | Out-Null
}
foreach ($name in @('run.ps1', 'create_profile.ps1')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $global:FakePackage "scripts/$name")
}
'module core; endmodule' | Set-Content -LiteralPath (Join-Path $global:FakePackage 'rtl/core.sv')
$rows = foreach ($name in @('scripts/run.ps1', 'rtl/core.sv')) { ('0' * 64) + "  $name" }
$rows | Set-Content -LiteralPath (Join-Path $global:FakePackage 'SHA256SUMS')
$runner = Join-Path $global:FakePackage 'scripts/run.ps1'
$fake = Join-Path $PSScriptRoot 'fake_vivado.ps1'
$records = @{}
$env:ARA_FPGA_PROFILE = 'inherited-value-must-be-restored'
foreach ($profile in @('baseline', 'host', 'dual_ddr')) {
    $global:ExpectedProfile = $profile
    $projectName = 'ara_dsa_vcu118'
    $state = Join-Path $global:FakePackage 'build/managed'
    if ($profile -ne 'baseline') {
        $projectName += "_$profile"
        $state = Join-Path $state $profile
    }
    $projectDir = Join-Path $global:FakePackage "build/$projectName"
    New-Item -ItemType Directory -Path $projectDir | Out-Null
    'test xpr' | Set-Content -LiteralPath (Join-Path $projectDir "$projectName.xpr")
    & $runner -Stage all -Profile $profile -Vivado $fake -RunRoot (Join-Path $base 'runs')
    Assert ($env:ARA_FPGA_PROFILE -eq 'inherited-value-must-be-restored') 'environment restored after success'
    $record = Get-Content -Raw -LiteralPath (Join-Path $state 'latest_synth.json') | ConvertFrom-Json
    Assert ($record.Profile -eq $profile) 'provenance includes selected profile'
    Assert ($record.Project -eq (Join-Path $projectDir "$projectName.xpr")) 'isolated project'
    $records[$profile] = $record
    $before = $global:FakeCalls
    & $runner -Stage impl -Profile $profile -Vivado $fake -RunRoot (Join-Path $base 'runs')
    Assert ($global:FakeCalls -eq $before + 1) 'resume only selected profile implementation'
    Assert ($global:FakeParent -eq $record.Run) 'resume exact selected synthesis'
    Write-Host "PASS managed profile $profile"
}
Assert (@($records.Values.InputHash | Select-Object -Unique).Count -eq 3) 'profile participates in input hash'
Assert (@($records.Values.Run | Select-Object -Unique).Count -eq 3) 'separate synthesis records'
$hostState = Join-Path $global:FakePackage 'build/managed/host/latest_synth.json'
$baselineState = Join-Path $global:FakePackage 'build/managed/latest_synth.json'
Copy-Item -LiteralPath $baselineState -Destination $hostState -Force
$global:ExpectedProfile = 'host'
$before = $global:FakeCalls
$caught = ''
try { & $runner -Stage impl -Profile host -Vivado $fake -RunRoot (Join-Path $base 'runs') }
catch { $caught = $_.ToString() }
Assert ($caught.Contains('Inputs/project changed')) 'cross-profile parent rejected'
Assert ($global:FakeCalls -eq $before) 'no child launch for cross-profile parent'
Assert ($env:ARA_FPGA_PROFILE -eq 'inherited-value-must-be-restored') 'environment restored on failure'

# All profiles, including creation, must share the same lock.
$lockPath = Join-Path $global:FakePackage 'build/managed/run.lock'
$held = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
try {
    foreach ($script in @($runner, (Join-Path $global:FakePackage 'scripts/create_profile.ps1'))) {
        $caught = ''
        try { & $script -Profile host -Vivado $fake }
        catch { $caught = $_.ToString() }
        Assert ($caught -ne '') 'held cross-profile lock rejects run/prepare'
    }
} finally { $held.Dispose() }
Assert ($global:FakeCalls -eq $before) 'held lock never reaches Vivado'
Assert ($env:ARA_FPGA_PROFILE -eq 'inherited-value-must-be-restored') 'creation failure restores environment'
Write-Host 'PASS profile fingerprints, provenance, resume, lock and environment cleanup'
Write-Host "Test evidence: $base"
