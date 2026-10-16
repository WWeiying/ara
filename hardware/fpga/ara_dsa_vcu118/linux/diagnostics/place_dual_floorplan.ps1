param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$bundle='D:\fpga_runs\ara_dual_reset_locality_20261005_01'
$checkpoint="$bundle\implementation_01\impl_reset_249eae2d3065\ara_dsa_vcu118_opt.dcp"
$tools="$bundle\continuation_tools"
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
if(Test-Path "$Root\started.json"){throw 'Output already used'}
$inputs=@{}
foreach($p in @($checkpoint,$PSCommandPath,"$Root\dual_floorplan.tcl","$Root\place_dual_floorplan.tcl",
    "$tools\dual_cdc_preflight.tcl","$tools\check_dual_reset_netlist.tcl","$tools\dual_slr_locality.tcl")){
    $inputs[$p]=(Get-FileHash $p).Hash
}
@{Started=(Get-Date -Format o);Inputs=$inputs;BoardModified=$false;PlacementAttempts=1;
  Scope='Fresh optimized dual-DDR netlist; physical constraints only; no board access'} |
  ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\place_dual_floorplan.tcl" -log "$Root\vivado.log" -tclargs $checkpoint $tools "$bundle\package" $Root
    $code=$LASTEXITCODE
    foreach($p in $inputs.Keys){if((Get-FileHash $p).Hash -ne $inputs[$p]){throw "Input changed: $p"}}
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;Scope='Execution only, not timing signoff'} |
        ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
