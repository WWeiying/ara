# Reuse one immutable routed DCP; no synthesis, RTL edits, or board access.
param(
    [Parameter(Mandatory=$true)][string]$Checkpoint,
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][string]$Out,
    [string]$Vivado='D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Checkpoint=(Get-Item -LiteralPath $Checkpoint).FullName
$Package=(Resolve-Path -LiteralPath $Package).Path
$Out=[IO.Path]::GetFullPath($Out)
if ((Get-Item -LiteralPath $Checkpoint).Length -eq 0 -or
    [IO.Path]::GetExtension($Checkpoint) -ne '.dcp') {throw 'Missing routed DCP'}
if (Test-Path -LiteralPath $Out) {throw 'Output already exists'}
if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {
    throw 'Another Vivado process is active'
}
New-Item -ItemType Directory -Path $Out | Out-Null
$oldProfile=$env:ARA_FPGA_PROFILE
$lock=$null
function Save-State([string]$Stage,[string]$Message='') {
    @{Stage=$Stage; Message=$Message; Updated=(Get-Date -Format o);
      Checkpoint=$Checkpoint; BoardModified=$false} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $Out 'state.json') -Encoding UTF8
}
Start-Transcript -LiteralPath (Join-Path $Out 'flow.log') -NoClobber
try {
    $lock=[IO.File]::Open((Join-Path $Package 'build\managed\run.lock'),
                          'OpenOrCreate','ReadWrite','None')
    if ((Get-FileHash "$Package\SHA256SUMS").Hash.ToLower() -ne
        '2afcd0d742ea8a290c1b65131c01ace4ac8dbd4d6d2ca530b2c628aa287dd25a') {
        throw 'Frozen package inventory changed'
    }
    & py -3 "$Package\scripts\verify_package.py"
    if ($LASTEXITCODE -ne 0) {throw 'Frozen package verification failed'}
    $checkpointHash=(Get-FileHash -LiteralPath $Checkpoint).Hash
    $toolHash=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'close_routed_setup.tcl')).Hash
    $gateHash=(Get-FileHash -LiteralPath (Join-Path $Package 'scripts\run_support.tcl')).Hash
    @{CheckpointSHA256=$checkpointHash; ToolSHA256=$toolHash; GateSHA256=$gateHash;
      Intent='Post-route setup closure; strict route/setup/hold/pulse gate';
      AutomaticProgramming=$false} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $Out 'inputs.json') -Encoding UTF8
    $env:ARA_FPGA_PROFILE='host_ethernet'
    Save-State 'running'
    Push-Location -LiteralPath $Out
    try {
        & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'close_routed_setup.tcl') `
            -log session.log -journal session.jou -tclargs $Checkpoint $Out $Package
        if ($LASTEXITCODE -ne 0) {throw 'Post-route closure failed; inspect session.log'}
    } finally {Pop-Location}
    if ((Get-FileHash -LiteralPath $Checkpoint).Hash -ne $checkpointHash -or
        (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'close_routed_setup.tcl')).Hash -ne $toolHash -or
        (Get-FileHash -LiteralPath (Join-Path $Package 'scripts\run_support.tcl')).Hash -ne $gateHash) {
        throw 'Checkpoint or tool changed during closure'
    }
    $stage=(Get-Content -LiteralPath (Join-Path $Out 'stage.txt') -Raw).Trim()
    if ($stage -ne 'timing_passed_needs_full_audit') {throw "Unexpected stage: $stage"}
    $result=Join-Path $Out 'ara_dsa_vcu118_routed.dcp'
    if (!(Test-Path -LiteralPath $result) -or !(Get-Item -LiteralPath $result).Length) {
        throw 'Missing optimized checkpoint'
    }
    Get-FileHash -LiteralPath $result | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $Out 'output_hash.json') -Encoding UTF8
    Save-State $stage
} catch {
    Save-State 'failed' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    $env:ARA_FPGA_PROFILE=$oldProfile
    if ($null -ne $lock) {$lock.Dispose()}
    Stop-Transcript
}
