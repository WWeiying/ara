#requires -Version 5.1
# Audit a saved routed design without opening the XPR or rebuilding it.
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Checkpoint,
    [string]$Vivado = 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat',
    [string]$RunRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-AuditScriptHashes {
    $hashes = [ordered]@{}
    foreach ($name in @('audit_routed.ps1', 'audit_routed.tcl', 'audit_support.tcl',
                       'common.tcl', 'config.tcl', 'constraint_checks.tcl', 'warning_details.tcl')) {
        $hashes[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
    }
    return ($hashes | ConvertTo-Json -Compress)
}

if (!$Checkpoint) { throw 'Usage: .\scripts\audit_routed.ps1 <path_to_routed.dcp>' }
$inputFile = Get-Item -LiteralPath $Checkpoint
if ($inputFile.PSIsContainer -or $inputFile.Extension -ine '.dcp' -or $inputFile.Length -le 0) {
    throw 'Checkpoint must be an existing, nonempty .dcp file.'
}
$Checkpoint = $inputFile.FullName
$Vivado = (Get-Command $Vivado -ErrorAction Stop).Source
$root = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $root 'build/managed'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$lock = $null
$inputHandle = $null
try {
    try {
        $lock = [IO.File]::Open((Join-Path $stateDir 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        throw "Cannot acquire $stateDir/run.lock. Another managed run may be active; do not delete the lock file."
    }
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'")
    if ($existing.Count) { throw 'Close existing Vivado sessions before auditing. No process was killed.' }
    # Permit Vivado to read the checkpoint, but not overwrite/delete it.
    $inputHandle = [IO.File]::Open($Checkpoint, 'Open', 'Read', 'Read')
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Checkpoint).Hash
    $scriptHashes = Get-AuditScriptHashes
    if (!$RunRoot) { $RunRoot = Join-Path ([IO.Path]::GetPathRoot($root)) 'fpga_runs' }
    $token = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $name = "audit_$token"
    $reports = Join-Path $root "reports/$name"
    if (Test-Path -LiteralPath $reports) { throw "Report directory already exists: $reports" }
    $session = Join-Path $RunRoot ("ara_audit_" + (Get-Date -Format yyyyMMdd_HHmmss) + "_$token")
    New-Item -ItemType Directory -Path $session | Out-Null
    $session = (Resolve-Path -LiteralPath $session).Path
    $record = [ordered]@{
        Mode = 'routed checkpoint only'; Checkpoint = $Checkpoint; SHA256 = $hash
        Length = $inputHandle.Length; Audit = $name; Reports = $reports; Directory = $session
        ScriptHashes = ($scriptHashes | ConvertFrom-Json)
        BitstreamGenerated = $false; ManualReviewRequired = $true
    }
    $record | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $session 'audit_input.json') -Encoding UTF8
    Write-Host "Checkpoint: $Checkpoint"
    Write-Host "Reports: $reports"
    Write-Host "Audit logs: $session"
    Write-Host 'No synthesis, placement, routing, current RTL/XDC load, or bitstream generation.'
    Push-Location -LiteralPath $session
    try {
        & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'audit_routed.tcl') `
            -log session.log -journal session.jou -tclargs $Checkpoint $session $token
        if ($LASTEXITCODE -ne 0) { throw "Checkpoint audit failed. Inspect $session/session.log and $reports." }
        if ((Get-AuditScriptHashes) -ne $scriptHashes -or
            (Get-FileHash -Algorithm SHA256 -LiteralPath $Checkpoint).Hash -ne $hash) {
            throw 'Audit scripts or checkpoint changed. Results were not accepted.'
        }
        $done = (Get-Content -Raw -LiteralPath (Join-Path $session 'completed_audit.txt')).Trim()
        if ($done -ne $name) { throw 'Missing or mismatched audit completion record' }
        $record['AutomatedChecksPassed'] = $true
        $record | ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath (Join-Path $session 'completed_audit.json') -Encoding UTF8
        Write-Host "SUCCESS: checkpoint automated checks passed; reports: $reports"
        Write-Host 'Review CDC, DRC, methodology and timing coverage. The old flow status was not changed.'
    } finally { Pop-Location }
} finally {
    if ($null -ne $inputHandle) { $inputHandle.Dispose() }
    if ($null -ne $lock) { $lock.Dispose() }
}
