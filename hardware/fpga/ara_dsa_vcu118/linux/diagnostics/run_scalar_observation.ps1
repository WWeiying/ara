#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Inputs,
      [Parameter(Mandatory=$true)][string]$RunDir)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$package='D:\fpga_runs\ara_mainrtl_20260930\package'
$synth='D:\fpga_runs\ara_mainrtl_20260930\runs\synth_3d28a8eb257a\ara_dsa_vcu118.dcp'
$synthHash='28998C0C59EE7FA6880508CAEF119C6EB7B5841E577BAF36EA2B98B324712FDB'
$reference='D:\fpga_runs\ara_mainrtl_finalize_20261001\runs\ara_dsa_vcu118_routed.dcp'
$referenceHash='7884B794A6C41DE283C5E4AF00202E6268704CF70136FA7A3D09A33A58A16D8E'
if(Test-Path -LiteralPath $RunDir){throw 'Existing output; no restart or overwrite'}
if(@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count){throw 'Vivado already active'}
$bindings=Get-Content (Join-Path $Inputs 'bindings.json') -Raw | ConvertFrom-Json
$width=$bindings.physical_nets.Count
if($bindings.profile -ne 'scalar_cache_mmu_stall' -or
   !$bindings.candidate_sources_resolved -or $bindings.missing.Count -ne 0 -or
   $width -lt 1 -or $width -gt 1024){throw 'Invalid candidate profile'}
if((Get-FileHash $synth).Hash -ne $synthHash -or
   (Get-FileHash $reference).Hash -ne $referenceHash){throw 'Frozen input hash mismatch'}
if((Get-FileHash "$package\SHA256SUMS").Hash -ne
   '9DFEE610630BFC5F1087BA687A05E946623ABD4D569FF7417C6565F9E1CB61DD'){
   throw 'Frozen package inventory changed'
}
& py -3 "$package\scripts\verify_package.py"
if($LASTEXITCODE -ne 0){throw 'Frozen package verification failed'}
New-Item -ItemType Directory -Path $RunDir | Out-Null
foreach($name in @('bindings.json','connections.tsv')){Copy-Item (Join-Path $Inputs $name) $RunDir}
foreach($name in @('prepare_stall_ila.tcl','implement_stall_ila.tcl')){
    Copy-Item (Join-Path $PSScriptRoot $name) $RunDir
}
Get-FileHash (Join-Path $RunDir '*.tcl'),(Join-Path $RunDir '*.json'),(Join-Path $RunDir '*.tsv') |
    ConvertTo-Json | Set-Content (Join-Path $RunDir 'inputs_hashes.json') -Encoding UTF8
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$false;FunctionalRTLModified=$false;AutomaticProgramming=$false;
      ProbeWidth=$width;SynthSHA256=$synthHash;ReferenceSHA256=$referenceHash;
      HardwareValidated=$false} | ConvertTo-Json |
      Set-Content (Join-Path $RunDir 'state.json') -Encoding UTF8
}
try {
    Set-Location $RunDir
    State 'preparing_scalar_observation'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
      -log (Join-Path $RunDir 'prepare.log') -source (Join-Path $RunDir 'prepare_stall_ila.tcl') `
      -tclargs $package synth_3d28a8eb257a (Join-Path $RunDir 'connections.tsv') (Join-Path $RunDir 'prepared')
    if($LASTEXITCODE -ne 0){throw 'Observation preparation failed'}
    $marker=Get-Content (Join-Path $RunDir 'prepared\prepared.txt') -Raw
    if($marker -notmatch "(?m)^probe_width=$width clock=clk_50_clkwiz\r?$"){
        throw 'Unexpected prepared clock/width'
    }
    State 'incremental_implementation'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
      -log (Join-Path $RunDir 'implementation.log') -source (Join-Path $RunDir 'implement_stall_ila.tcl') `
      -tclargs (Join-Path $RunDir 'prepared\observation_synth.dcp') $reference $package `
      (Join-Path $RunDir 'physical') $width
    if($LASTEXITCODE -ne 0){throw 'Implementation or timing gate failed; preserve reports'}
    if((Get-Content (Join-Path $RunDir 'physical\stage.txt') -Raw).Trim() -ne
        'timing_passed_requires_full_audit'){throw 'Completion marker missing'}
    if((Get-FileHash $synth).Hash -ne $synthHash -or
       (Get-FileHash $reference).Hash -ne $referenceHash){throw 'Frozen inputs changed'}
    State 'timing_passed_requires_probe_and_full_audit' 'No bitstream or board programming'
} catch { State 'failed' ($_|Out-String); exit 1 }
