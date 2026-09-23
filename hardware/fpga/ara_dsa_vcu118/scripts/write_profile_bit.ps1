#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RunDir,
    [ValidateSet('baseline', 'host', 'dual_ddr')][string]$Profile = 'baseline',
    [string]$Out,
    [string]$Vivado = 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$run = (Resolve-Path -LiteralPath $RunDir).Path
if (!(Test-Path -LiteralPath $run -PathType Container)) { throw 'RunDir must be a directory.' }
$dcps = @(Get-ChildItem -LiteralPath $run -Recurse -File -Filter '*_routed.dcp')
if ($dcps.Count -ne 1) {
    throw "Expected exactly one routed DCP in $run; found $($dcps.Count). Specify the exact run directory."
}
$checkpoint = $dcps[0].FullName
if (!$dcps[0].Length) { throw "Empty routed DCP: $checkpoint" }
$flowPath = Join-Path $run 'completed_flow.json'
if (Test-Path -LiteralPath $flowPath) {
    $flow = Get-Content -LiteralPath $flowPath -Raw | ConvertFrom-Json
    if ($flow.PSObject.Properties.Name -contains 'Profile' -and $flow.Profile -ne $Profile) {
        throw "Run profile is $($flow.Profile), not $Profile. Select the matching -Profile."
    }
}
if (!$Out) { $Out = Join-Path $run "bitstream_$Profile" }
$Out = [IO.Path]::GetFullPath($Out)
if (Test-Path -LiteralPath $Out) { throw "Output directory already exists: $Out. Select a new -Out." }
$Vivado = (Get-Command $Vivado -ErrorAction Stop).Source
$managed = Join-Path (Split-Path -Parent $PSScriptRoot) 'build\managed'
New-Item -ItemType Directory -Force -Path $managed | Out-Null
$lock = $null
$previousProfile = $env:ARA_FPGA_PROFILE
try {
    $lock = [IO.File]::Open((Join-Path $managed 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'")
    if ($existing.Count) { throw 'Close Vivado GUI/workers first; no process was killed.' }
    $env:ARA_FPGA_PROFILE = $Profile
    New-Item -ItemType Directory -Path $Out | Out-Null
    Write-Host "Profile: $Profile; checkpoint: $checkpoint"
    Write-Host "Outputs and validation reports: $Out"
    Push-Location -LiteralPath $Out
    try {
        & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'write_profile_bit.tcl') `
            -log session.log -journal session.jou -tclargs $checkpoint $Out
        if ($LASTEXITCODE -ne 0) { throw "Bitstream generation failed; inspect $Out\session.log" }
        $outputs = foreach ($ext in @('bit', 'ltx')) {
            $path = Join-Path $Out "ara_dsa_vcu118.$ext"
            if (!(Test-Path -LiteralPath $path) -or !(Get-Item -LiteralPath $path).Length) {
                throw "Missing/empty output: $path"
            }
            Get-FileHash -LiteralPath $path -Algorithm SHA256
        }
        @{ Profile = $Profile; Checkpoint = $checkpoint;
           CheckpointSHA256 = (Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash;
           Outputs = $outputs } | ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath (Join-Path $Out 'bitstream.json') -Encoding UTF8
        Write-Host "SUCCESS: bitstream and probes saved to $Out"
    } finally { Pop-Location }
} finally {
    $env:ARA_FPGA_PROFILE = $previousProfile
    if ($null -ne $lock) { $lock.Dispose() }
}
