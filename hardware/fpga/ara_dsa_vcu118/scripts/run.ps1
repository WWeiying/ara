#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('synth', 'impl')][string]$Stage = 'synth',
    [string]$Vivado = 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat',
    [string]$RunRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-InputFingerprint([string]$Root) {
    $rows = foreach ($row in Get-Content -LiteralPath (Join-Path $Root 'SHA256SUMS')) {
        if ($row -notmatch '^[0-9a-f]{64}  (.+)$') { throw 'Invalid SHA256SUMS entry' }
        $name = $Matches[1]
        if ($name -match '^(rtl/|scripts/|constraints/|board_files/|manifest\.json$)') {
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root $name)).Hash
            "$hash  $name"
        }
    }
    if ($null -eq $rows) { throw 'No build inputs found in SHA256SUMS' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
    } finally { $sha.Dispose() }
}

$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root 'build\ara_dsa_vcu118\ara_dsa_vcu118.xpr'
if (!(Test-Path -LiteralPath $project -PathType Leaf)) {
    throw "Existing project required: $project. This command never recreates the project or IP."
}
$Vivado = (Get-Command $Vivado -ErrorAction Stop).Source
$stateDir = Join-Path $root 'build\managed'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$lock = $null
$pushed = $false
try {
    # Keep the handle for the entire child lifetime. Never unlink a held lock.
    try {
        $lock = [IO.File]::Open((Join-Path $stateDir 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        throw "Cannot acquire $stateDir\run.lock. Check other managed runs and directory permissions; do not delete the lock file. $($_.Exception.Message)"
    }

    # GUI command lines do not reliably identify their open XPR. Fail closed.
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'")
    if ($existing.Count) {
        $details = $existing | Select-Object ProcessId, CreationDate, CommandLine | Format-List | Out-String
        throw "Vivado processes already exist. Save/close the GUI and inspect leftover workers first. No process was killed.`n$details"
    }

    $fingerprint = Get-InputFingerprint $root
    $latest = Join-Path $stateDir 'latest_synth.json'
    $parent = '-'
    if ($Stage -eq 'impl') {
        if (!(Test-Path -LiteralPath $latest)) { throw 'Run this script with -Stage synth successfully first.' }
        $record = Get-Content -Raw -LiteralPath $latest | ConvertFrom-Json
        if ($record.Project -ne $project -or $record.InputHash -ne $fingerprint) {
            throw 'Inputs/project changed since the recorded synthesis. Run -Stage synth again.'
        }
        $parent = $record.Run
        if ($parent -notmatch '^synth_[0-9a-f]{12}$') { throw 'Invalid recorded synthesis run' }
    }
    if (!$RunRoot) { $RunRoot = Join-Path ([IO.Path]::GetPathRoot($root)) 'fpga_runs' }
    $token = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $session = Join-Path $RunRoot ("ara_" + (Get-Date -Format yyyyMMdd_HHmmss) + "_$token")
    New-Item -ItemType Directory -Path $session | Out-Null
    $session = (Resolve-Path -LiteralPath $session).Path
    Copy-Item -LiteralPath $project -Destination (Join-Path $session 'project_before.xpr')
    Write-Host "Project: $project"
    Write-Host "Stage: $Stage; results: $session"
    Write-Host 'Keep this terminal open. Do not edit/update the project sources during the run.'
    Push-Location -LiteralPath $session
    $pushed = $true
    & $Vivado -mode batch -source (Join-Path $PSScriptRoot 'run.tcl') `
        -log session.log -journal session.jou -tclargs $Stage $session $token $parent
    if ($LASTEXITCODE -ne 0) { throw "Vivado failed. Inspect $session\session.log and the printed run directory." }
    if ((Get-InputFingerprint $root) -ne $fingerprint) {
        throw "Inputs changed during the run. Results in $session were NOT accepted; rerun with stable inputs."
    }
    $run = (Get-Content -Raw -LiteralPath (Join-Path $session 'completed_run.txt')).Trim()
    if ($run -ne "${Stage}_$token") { throw 'Missing or mismatched completion record' }
    if ($Stage -eq 'synth') {
        $record = @{ Project = $project; Run = $run; InputHash = $fingerprint; Directory = $session }
        $temp = Join-Path $stateDir "latest_$token.tmp"
        $record | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $latest -Force
    }
    Write-Host "SUCCESS: $run; results: $session"
} finally {
    if ($pushed) { Pop-Location }
    if ($null -ne $lock) { $lock.Dispose() }
}
