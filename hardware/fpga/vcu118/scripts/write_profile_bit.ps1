#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RunDir,
    [ValidateSet('baseline', 'host', 'dual_ddr')][string]$Profile = 'baseline',
    [string]$Out,
    [string]$AuditManifest,
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
$inputHandle = $null
$previousProfile = $env:ARA_FPGA_PROFILE
try {
    $lock = [IO.File]::Open((Join-Path $managed 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'")
    if ($existing.Count) { throw 'Close Vivado GUI/workers first; no process was killed.' }
    $inputHandle = [IO.File]::Open($checkpoint, 'Open', 'Read', 'Read')
    $checkpointHash = (Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash
    $mode = 'full'
    $auditHash = $null
    if ($AuditManifest) {
        $AuditManifest = (Resolve-Path -LiteralPath $AuditManifest -ErrorAction Stop).Path
        $auditHash = (Get-FileHash -LiteralPath $AuditManifest -Algorithm SHA256).Hash
        $audit = Get-Content -LiteralPath $AuditManifest -Raw | ConvertFrom-Json
        if ($audit.AutomatedChecksPassed -ne $true -or $audit.Mode -ne 'routed checkpoint only' -or
            $audit.Profile -ne $Profile -or $audit.Checkpoint -ne $checkpoint -or
            $audit.SHA256 -ne $checkpointHash -or $audit.Length -ne $inputHandle.Length) {
            throw 'Audit manifest does not certify this profile and routed checkpoint.'
        }
        $reports = (Resolve-Path -LiteralPath $audit.Reports -ErrorAction Stop).Path
        if ($audit.Audit -ne (Split-Path -Leaf $reports) -or
            (Join-Path $audit.Directory 'completed_audit.json') -ne $AuditManifest -or
            (Get-Content -LiteralPath (Join-Path $audit.Directory 'completed_audit.txt') -Raw).Trim() -ne $audit.Audit) {
            throw 'Audit manifest, reports directory and completion marker disagree.'
        }
        foreach ($name in @('audit_routed.ps1', 'audit_routed.tcl', 'audit_support.tcl',
                            'common.tcl', 'config.tcl', 'constraint_checks.tcl', 'warning_details.tcl')) {
            $recorded = $audit.ScriptHashes.PSObject.Properties[$name]
            if ($null -eq $recorded -or $recorded.Value -ne
                (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash) {
                throw "Audit script changed or is missing from manifest: $name"
            }
        }
        $reportFiles = @(Get-ChildItem -LiteralPath $reports -File -Filter '*.rpt')
        $recordedReports = @($audit.ReportHashes.PSObject.Properties.Name)
        foreach ($required in @('route_status.rpt', 'timing_summary.rpt', 'check_timing.rpt',
                                'cdc.rpt', 'drc.rpt', 'methodology.rpt', 'constraint_checks.rpt',
                                'boundary_checks.rpt', 'multiple_drivers.rpt')) {
            if ($required -notin $recordedReports) { throw "Audit report missing from manifest: $required" }
        }
        if ($reportFiles.Count -ne $recordedReports.Count) { throw 'Audit report inventory changed.' }
        foreach ($file in $reportFiles) {
            $recorded = $audit.ReportHashes.PSObject.Properties[$file.Name]
            if ($file.Length -le 0 -or $null -eq $recorded -or $recorded.Value -ne
                (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash) {
                throw "Audit report changed or is empty: $($file.FullName)"
            }
        }
        $mode = 'audited'
    }
    $env:ARA_FPGA_PROFILE = $Profile
    New-Item -ItemType Directory -Path $Out | Out-Null
    Write-Host "Profile: $Profile; checkpoint: $checkpoint"
    Write-Host "Report mode: $mode; outputs: $Out"
    Push-Location -LiteralPath $Out
    try {
        & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'write_profile_bit.tcl') `
            -log session.log -journal session.jou -tclargs $checkpoint $Out $mode
        if ($LASTEXITCODE -ne 0) { throw "Bitstream generation failed; inspect $Out\session.log" }
        if ((Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash -ne $checkpointHash -or
            ($mode -eq 'audited' -and (Get-FileHash -LiteralPath $AuditManifest -Algorithm SHA256).Hash -ne $auditHash)) {
            throw 'Checkpoint or audit manifest changed during bitstream generation.'
        }
        if ($mode -eq 'audited') {
            foreach ($name in @('audit_routed.ps1', 'audit_routed.tcl', 'audit_support.tcl',
                                'common.tcl', 'config.tcl', 'constraint_checks.tcl', 'warning_details.tcl')) {
                if ($audit.ScriptHashes.PSObject.Properties[$name].Value -ne
                    (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash) {
                    throw "Audit script changed during bitstream generation: $name"
                }
            }
            foreach ($file in $reportFiles) {
                if ($audit.ReportHashes.PSObject.Properties[$file.Name].Value -ne
                    (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash) {
                    throw "Audit report changed during bitstream generation: $($file.FullName)"
                }
            }
        }
        $outputs = foreach ($ext in @('bit', 'ltx')) {
            $path = Join-Path $Out "ara_dsa_vcu118.$ext"
            if (!(Test-Path -LiteralPath $path) -or !(Get-Item -LiteralPath $path).Length) {
                throw "Missing/empty output: $path"
            }
            Get-FileHash -LiteralPath $path -Algorithm SHA256
        }
        @{ Profile = $Profile; Checkpoint = $checkpoint; CheckpointSHA256 = $checkpointHash;
           ReportMode = $mode; AuditManifest = $AuditManifest; AuditManifestSHA256 = $auditHash;
           Outputs = $outputs } | ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath (Join-Path $Out 'bitstream.json') -Encoding UTF8
        Write-Host "SUCCESS: bitstream and probes saved to $Out"
    } finally { Pop-Location }
} finally {
    $env:ARA_FPGA_PROFILE = $previousProfile
    if ($null -ne $inputHandle) { $inputHandle.Dispose() }
    if ($null -ne $lock) { $lock.Dispose() }
}
