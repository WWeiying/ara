#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('baseline', 'host', 'dual_ddr')][string]$Profile = 'baseline',
    [string]$Vivado = 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Vivado = (Get-Command $Vivado -ErrorAction Stop).Source
$root = Split-Path -Parent $PSScriptRoot
$managed = Join-Path $root 'build\managed'
New-Item -ItemType Directory -Force -Path $managed | Out-Null
$lock = $null
$previousProfile = $env:ARA_FPGA_PROFILE
try {
    # Same cross-profile lock as run.ps1; shared sources must stay stable.
    $lock = [IO.File]::Open((Join-Path $managed 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'")
    if ($existing.Count) { throw 'Close Vivado GUI/workers first; no process was killed.' }
    $env:ARA_FPGA_PROFILE = $Profile
    $session = Join-Path $managed ("prepare_${Profile}_" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $session | Out-Null
    Write-Host "Profile: $Profile; logs: $session"
    Write-Host 'Keep sources unchanged until IP preparation finishes.'
    Push-Location -LiteralPath $session
    try {
        & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'prepare_profile.tcl') `
            -log session.log -journal session.jou
        if ($LASTEXITCODE -ne 0) { throw "Profile preparation failed; inspect $session\session.log" }
    } finally { Pop-Location }
} finally {
    $env:ARA_FPGA_PROFILE = $previousProfile
    if ($null -ne $lock) { $lock.Dispose() }
}
