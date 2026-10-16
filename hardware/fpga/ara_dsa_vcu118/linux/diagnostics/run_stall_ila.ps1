#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Preparation = 'D:\fpga_runs\ara_stall_ila_prepare_20261002_02',
    [string]$RunDir = 'D:\fpga_runs\ara_stall_ila_implementation_20261002',
    [int]$PreparationProcessId = 0
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$package = 'D:\fpga_runs\ara_mainrtl_20260930\package'
$reference = 'D:\fpga_runs\ara_mainrtl_finalize_20261001\runs\ara_dsa_vcu118_routed.dcp'
$referenceHash = '7884B794A6C41DE283C5E4AF00202E6268704CF70136FA7A3D09A33A58A16D8E'
$synth = 'D:\fpga_runs\ara_mainrtl_20260930\runs\synth_3d28a8eb257a\ara_dsa_vcu118.dcp'
$synthHash = '28998C0C59EE7FA6880508CAEF119C6EB7B5841E577BAF36EA2B98B324712FDB'
$prepared = Join-Path $Preparation 'prepared\observation_synth.dcp'
if (Test-Path -LiteralPath $RunDir) { throw 'Output already exists; do not overwrite or restart' }
if ($PreparationProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$PreparationProcessId"
    if ($null -ne $process) {
        if ($process.Name -ne 'powershell.exe' -or
            $process.CommandLine -notlike '*-File D:\fpga_runs\ara_board_tools_20261002\ara_stall_ila_prepare.ps1*') {
            throw 'Preparation PID does not identify the expected preparation script'
        }
        Wait-Process -Id $PreparationProcessId -Timeout 7200
    }
}
$prepState = Get-Content (Join-Path $Preparation 'state.json') -Raw | ConvertFrom-Json
if ($prepState.Stage -ne 'prepared_not_implemented_or_programmed' -or
    $prepState.BoardModified -ne $false -or $prepState.SHA256 -ne $synthHash) {
    throw 'Preparation has not passed'
}
$marker = Get-Content (Join-Path $Preparation 'prepared\prepared.txt') -Raw
if ($marker -notmatch '(?m)^observation_only_prepared_not_implemented\r?$' -or
    $marker -notmatch '(?m)^probe_width=579 clock=clk_50_clkwiz\r?$') {
    throw 'Unexpected prepared probe configuration'
}
if ((Get-FileHash $reference).Hash -ne $referenceHash -or
    (Get-FileHash $synth).Hash -ne $synthHash) { throw 'Frozen input hash mismatch' }
$preparedHash = (Get-FileHash $prepared).Hash
New-Item -ItemType Directory -Path $RunDir | Out-Null
function State([string]$stage, [string]$message = '') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      BoardModified=$false; AutomaticProgramming=$false; FunctionalRTLModified=$false;
      Prepared=$prepared; PreparedSHA256=$preparedHash; Reference=$reference;
      ReferenceSHA256=$referenceHash; Profile='host_ethernet'; HardwareValidated=$false} |
        ConvertTo-Json | Set-Content (Join-Path $RunDir 'state.json') -Encoding UTF8
}
try {
    State 'validated_inputs'
    $script = Join-Path $RunDir 'implement_stall_ila.tcl'
    Copy-Item (Join-Path $PSScriptRoot 'implement_stall_ila.tcl') $script
    Copy-Item (Join-Path $Preparation 'bindings.json') (Join-Path $RunDir 'bindings.json')
    Copy-Item (Join-Path $Preparation 'prepared\validated.tsv') (Join-Path $RunDir 'validated.tsv')
    Set-Location $RunDir
    State 'observation_implementation'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -log (Join-Path $RunDir 'vivado.log') -source $script `
        -tclargs $prepared $reference $package (Join-Path $RunDir 'physical') 579
    if ($LASTEXITCODE -ne 0) { throw 'Observation implementation or timing gate failed' }
    $stage = (Get-Content (Join-Path $RunDir 'physical\stage.txt') -Raw).Trim()
    if ($stage -ne 'timing_passed_requires_full_audit') { throw 'Missing implementation completion' }
    if ((Get-FileHash $prepared).Hash -ne $preparedHash -or
        (Get-FileHash $reference).Hash -ne $referenceHash -or
        (Get-FileHash $synth).Hash -ne $synthHash) { throw 'Input changed during implementation' }
    State 'timing_passed_requires_full_audit' 'No bitstream or board programming requested'
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
}
