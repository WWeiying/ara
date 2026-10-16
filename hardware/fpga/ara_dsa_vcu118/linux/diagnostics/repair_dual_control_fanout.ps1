param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$bundle='D:\fpga_runs\ara_dual_reset_locality_20261005_01'
$checkpoint='D:\fpga_runs\ara_dual_placement_repair_20261006_01\repaired_placed.dcp'
$tools="$bundle\continuation_tools"
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
if(Test-Path "$Root\started.json"){throw 'Output already used'}
$hashes=@{}
foreach($path in @($checkpoint,"$tools\dual_cdc_preflight.tcl","$Root\repair_dual_control_fanout.tcl",$PSCommandPath)){
    $hashes[$path]=(Get-FileHash $path).Hash
}
@{Started=(Get-Date -Format o);Inputs=$hashes;BoardModified=$false;
  Scope='Measured control replication; no synthesis, no RTL edit, no board access'} |
  ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\repair_dual_control_fanout.tcl" -log "$Root\vivado.log" -tclargs $checkpoint $tools "$bundle\package" $Root
    $code=$LASTEXITCODE
    foreach($path in $hashes.Keys){if((Get-FileHash $path).Hash -ne $hashes[$path]){throw "Input changed: $path"}}
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;Scope='Execution only, not timing signoff'} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
