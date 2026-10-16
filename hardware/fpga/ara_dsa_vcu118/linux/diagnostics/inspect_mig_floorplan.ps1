param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
if(Test-Path "$Root\started.json"){throw 'Output already used'}
$checkpoint='D:\fpga_runs\ara_dual_floorplan_20261006_01\floorplanned_opt.dcp'
$package='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package'
$hash=(Get-FileHash $checkpoint).Hash
@{Started=(Get-Date -Format o);Checkpoint=$checkpoint;Hash=$hash;BoardModified=$false} |
    ConvertTo-Json | Set-Content "$Root\started.json"
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\inspect_mig_floorplan.tcl" -log "$Root\vivado.log" -tclargs $checkpoint $package $Root
    $code=$LASTEXITCODE
    if((Get-FileHash $checkpoint).Hash -ne $hash){throw 'Input changed'}
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;Scope='MIG initialization diagnosis, not timing signoff'} |
        ConvertTo-Json | Set-Content "$Root\result.json"
    exit $code
} finally {Pop-Location}
