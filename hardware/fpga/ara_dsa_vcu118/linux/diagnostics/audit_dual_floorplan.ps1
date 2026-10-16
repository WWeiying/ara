param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$checkpoint='D:\fpga_runs\ara_dual_control_repair_20261006_01\controls_placed.dcp'
$package='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package'
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
if(Test-Path "$Root\started.json"){throw 'Output already used'}
$inputs=@{}
foreach($p in @($checkpoint,$PSCommandPath,"$Root\audit_dual_floorplan.tcl")){$inputs[$p]=(Get-FileHash $p).Hash}
@{Started=(Get-Date -Format o);Inputs=$inputs;BoardModified=$false;Scope='Read-only floorplan audit'} |
    ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\audit_dual_floorplan.tcl" -log "$Root\vivado.log" -tclargs $checkpoint $package $Root
    $code=$LASTEXITCODE
    foreach($p in $inputs.Keys){if((Get-FileHash $p).Hash -ne $inputs[$p]){throw "Input changed: $p"}}
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false} | ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
