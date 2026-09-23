#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('all', 'synth', 'impl', 'inspect')][string]$Stage = 'synth',
    [ValidateSet('baseline', 'host', 'dual_ddr')][string]$Profile = 'baseline',
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
        $bytes = [Text.Encoding]::UTF8.GetBytes(("profile=$Profile`n" + ($rows -join "`n")))
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
    } finally { $sha.Dispose() }
}

function Assert-VivadoIdle {
    # GUI command lines do not reliably identify their open XPR. Fail closed.
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'")
    if ($existing.Count) {
        $details = $existing | Select-Object ProcessId, CreationDate, CommandLine | Format-List | Out-String
        throw "Vivado processes already exist. Save/close the GUI and inspect leftover workers first. No process was killed.`n$details"
    }
}

$root = Split-Path -Parent $PSScriptRoot
$projectName = 'ara_dsa_vcu118'
if ($Profile -ne 'baseline') { $projectName += "_$Profile" }
$project = Join-Path $root "build\$projectName\$projectName.xpr"
if (!(Test-Path -LiteralPath $project -PathType Leaf)) {
    throw "Existing project required: $project. Run scripts/create_profile.ps1 -Profile $Profile first."
}
$Vivado = (Get-Command $Vivado -ErrorAction Stop).Source
$stateDir = Join-Path $root 'build\managed'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$lockPath = Join-Path $stateDir 'run.lock'
if ($Profile -ne 'baseline') {
    $stateDir = Join-Path $stateDir $Profile
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
}
$previousProfile = $env:ARA_FPGA_PROFILE
$lock = $null
try {
    $env:ARA_FPGA_PROFILE = $Profile
    # Keep the handle for the entire child lifetime. Never unlink a held lock.
    try {
        $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        throw "Cannot acquire $lockPath. Check other managed runs and directory permissions; do not delete the lock file. $($_.Exception.Message)"
    }

    Assert-VivadoIdle

    $fingerprint = Get-InputFingerprint $root
    $latest = Join-Path $stateDir 'latest_synth.json'
    $parent = '-'
    if ($Stage -in @('impl', 'inspect')) {
        if (!(Test-Path -LiteralPath $latest)) { throw 'Run this script with -Stage synth successfully first.' }
        $record = Get-Content -Raw -LiteralPath $latest | ConvertFrom-Json
        if ($record.Project -ne $project -or ($Stage -eq 'impl' -and $record.InputHash -ne $fingerprint)) {
            throw 'Inputs/project changed since the recorded synthesis. Run -Stage synth again.'
        }
        $parent = $record.Run
        if ($parent -notmatch '^synth_[0-9a-f]{12}$') { throw 'Invalid recorded synthesis run' }
        if ($Stage -eq 'inspect') {
            Write-Host "INSPECT existing netlist $parent with current constraints; this does not validate new RTL."
        }
    }
    if (!$RunRoot) { $RunRoot = Join-Path ([IO.Path]::GetPathRoot($root)) 'fpga_runs' }
    $token = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $session = Join-Path $RunRoot ("ara_" + (Get-Date -Format yyyyMMdd_HHmmss) + "_$token")
    New-Item -ItemType Directory -Path $session | Out-Null
    $session = (Resolve-Path -LiteralPath $session).Path
    if ($Stage -eq 'inspect') {
        Copy-Item -LiteralPath $latest -Destination (Join-Path $session 'inspected_synth.json')
    }
    Copy-Item -LiteralPath $project -Destination (Join-Path $session 'project_before.xpr')
    Write-Host "Project: $project"
    Write-Host "Profile: $Profile; stage: $Stage; results: $session"
    Write-Host 'Keep this terminal open. Do not edit/update the project sources during the run.'
    $stages = @($Stage)
    if ($Stage -eq 'all') { $stages = @('synth', 'impl') }
    $completed = @()
    foreach ($currentStage in $stages) {
        # Keep one lock and one source fingerprint across the entire flow.
        Assert-VivadoIdle
        if ((Get-InputFingerprint $root) -ne $fingerprint) {
            throw "Inputs changed during the run. $currentStage was not launched."
        }
        $stageDir = $session
        if ($Stage -eq 'all') {
            $stageDir = Join-Path $session $currentStage
            New-Item -ItemType Directory -Path $stageDir | Out-Null
        }
        Write-Host "Running $currentStage; results: $stageDir"
        Push-Location -LiteralPath $stageDir
        try {
            & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'run.tcl') `
                -log session.log -journal session.jou -tclargs $currentStage $stageDir $token $parent
            if ($LASTEXITCODE -ne 0) { throw "Vivado failed. Inspect $stageDir\session.log and the printed run directory." }
            if ((Get-InputFingerprint $root) -ne $fingerprint) {
                throw "Inputs changed during the run. Results in $stageDir were NOT accepted; rerun with stable inputs."
            }
            $run = (Get-Content -Raw -LiteralPath (Join-Path $stageDir 'completed_run.txt')).Trim()
            if ($run -ne "${currentStage}_$token") { throw 'Missing or mismatched completion record' }
            if ($currentStage -eq 'synth') {
                $record = @{ Project = $project; Profile = $Profile; Run = $run; InputHash = $fingerprint; Directory = $stageDir }
                $temp = Join-Path $stateDir "latest_$token.tmp"
                $record | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
                Move-Item -LiteralPath $temp -Destination $latest -Force
                $parent = $run
            }
            if ($currentStage -eq 'inspect') {
                $reportDir = Join-Path $root "reports/$run"
                New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
                @{ InspectedSynthesis = $record; CurrentInputHash = $fingerprint;
                   Run = $run; Directory = $stageDir; Mode = 'old netlist, current constraints' } |
                    ConvertTo-Json -Depth 4 |
                    Set-Content -LiteralPath (Join-Path $reportDir 'inspection.json') -Encoding UTF8
            }
            $completed += @{ Run = $run; Directory = $stageDir; Reports = (Join-Path $root "reports/$run") }
            Write-Host "SUCCESS: $run; results: $stageDir"
        } finally { Pop-Location }
    }
    if ($Stage -eq 'all') {
        @{ Project = $project; Profile = $Profile; InputHash = $fingerprint; Runs = $completed; BitstreamGenerated = $false } |
            ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath (Join-Path $session 'completed_flow.json') -Encoding UTF8
        Write-Host "SUCCESS: full synthesis and routed implementation; results: $session"
        Write-Host 'No bitstream was generated. Review the routed reports before programming the board.'
    }
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
    $env:ARA_FPGA_PROFILE = $previousProfile
}
