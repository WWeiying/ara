# Reuse one reviewed synthesized project. Never reset, synthesize or program.
param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [Parameter(Mandatory=$true)][ValidatePattern('^synth_[0-9a-f]{12}$')][string]$ParentRun,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$InventorySHA256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$SynthesisReportSHA256,
    [Parameter(Mandatory=$true)][string]$Out,
    [switch]$ReviewedSynthesisPhysicalViolations,
    [string]$Vivado='D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if (!$ReviewedSynthesisPhysicalViolations) {throw 'Explicit synthesis hold/skew review authorization required'}
$Bundle=(Resolve-Path -LiteralPath $Bundle).Path
$package=Join-Path $Bundle 'package'
$Out=[IO.Path]::GetFullPath($Out)
if (Test-Path -LiteralPath $Out) {throw 'Output already exists; inspect instead of restarting'}
New-Item -ItemType Directory -Path $Out | Out-Null
$lock=$null
$oldProfile=$env:ARA_FPGA_PROFILE
function Save-State([string]$Stage,[string]$Message='') {
    @{Stage=$Stage; Message=$Message; Updated=(Get-Date -Format o); ProcessId=$PID;
      Profile='host_ethernet'; ParentRun=$ParentRun; BoardModified=$false} |
      ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Out 'state.json') -Encoding UTF8
}
function Verify-Inputs {
    if ((Get-FileHash "$package\SHA256SUMS").Hash.ToLower() -ne $InventorySHA256) {throw 'Inventory changed'}
    & py -3 "$package\scripts\verify_package.py"
    if ($LASTEXITCODE -ne 0) {throw 'Frozen input verification failed'}
    if ((Get-FileHash "$package\reports\$ParentRun\timing_summary.rpt").Hash.ToLower() -ne $SynthesisReportSHA256) {
        throw 'Synthesis report is not the reviewed report'
    }
}
Start-Transcript -LiteralPath (Join-Path $Out 'flow.log') -NoClobber
try {
    Save-State 'verify_snapshot'
    $lock=[IO.File]::Open("$package\build\managed\run.lock", 'OpenOrCreate', 'ReadWrite', 'None')
    if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {throw 'Vivado is busy; no process killed'}
    Verify-Inputs
    $toolFiles=@('continue_physical.ps1','continue_physical.tcl','continue_physical_support.tcl')
    $hashes=@{}
    foreach ($name in $toolFiles) {$hashes[$name]=(Get-FileHash (Join-Path $PSScriptRoot $name)).Hash}
    $token=[Guid]::NewGuid().ToString('N').Substring(0,12)
    @{Bundle=$Bundle; ParentRun=$ParentRun; InventorySHA256=$InventorySHA256;
      SynthesisReportSHA256=$SynthesisReportSHA256; ToolHashes=$hashes; Token=$token;
      Authorization='Reviewed synthesis hold/skew deferred to physical repair; strict routed gates';
      AutomaticProgramming=$false} | ConvertTo-Json -Depth 4 |
      Set-Content -LiteralPath (Join-Path $Out 'inputs.json') -Encoding UTF8
    $env:ARA_FPGA_PROFILE='host_ethernet'
    Save-State 'physical_flow_running'
    Push-Location -LiteralPath $Out
    try {
        & $Vivado -mode batch -notrace -source (Join-Path $PSScriptRoot 'continue_physical.tcl') `
            -log session.log -journal session.jou -tclargs $package $ParentRun $Out $token
        if ($LASTEXITCODE -ne 0) {throw 'Physical flow failed; inspect session.log and preserved reports'}
    } finally {Pop-Location}
    Verify-Inputs
    foreach ($name in $toolFiles) {
        if ((Get-FileHash (Join-Path $PSScriptRoot $name)).Hash -ne $hashes[$name]) {throw 'Continuation tools changed'}
    }
    $stage=(Get-Content -LiteralPath (Join-Path $Out 'stage.txt') -Raw).Trim()
    if ($stage -eq 'bitstream_complete_not_programmed') {
        $outputs=foreach ($ext in @('bit','ltx')) {
            $file=Join-Path $Out "bitstream_host_ethernet\ara_dsa_vcu118.$ext"
            if (!(Get-Item -LiteralPath $file).Length) {throw 'Empty bitstream/probes'}
            Get-FileHash -LiteralPath $file
        }
        $outputs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Out 'outputs.json') -Encoding UTF8
        Save-State $stage
    } elseif ($stage -eq 'review_required') {
        Save-State $stage (Get-Content -LiteralPath (Join-Path $Out 'review_required.txt') -Raw)
    } else {throw "Unexpected completion stage: $stage"}
} catch {
    Save-State 'failed' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    $env:ARA_FPGA_PROFILE=$oldProfile
    if ($null -ne $lock) {$lock.Dispose()}
    Stop-Transcript
}
