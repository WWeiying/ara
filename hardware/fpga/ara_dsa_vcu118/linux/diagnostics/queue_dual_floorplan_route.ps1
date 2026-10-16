param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Placement,
      [Parameter(Mandatory=$true)][string]$PlacementTask)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$task=$PlacementTask
$bundle='D:\fpga_runs\ara_dual_reset_locality_20261005_01'
if(Test-Path "$Root\started.json"){throw 'Output already used'}
function State($name,$message=''){
    @{Stage=$name;Message=$message;Updated=(Get-Date -Format o);BoardModified=$false} |
        ConvertTo-Json | Set-Content "$Root\state.json" -Encoding UTF8
}
@{Started=(Get-Date -Format o);Placement=$placement;Task=$task;BoardModified=$false} |
    ConvertTo-Json | Set-Content "$Root\started.json" -Encoding UTF8
try {
    State 'waiting_for_placement'
    while((Get-ScheduledTask -TaskName $task -ErrorAction Stop).State -eq 'Running'){
        Start-Sleep -Seconds 60
    }
    $result=Get-Content "$placement\result.json" -Raw | ConvertFrom-Json
    if($result.ExitCode -ne 0){throw 'Placement failed; no routing launched'}
    if((Get-Content "$placement\stage.txt" -Raw).Trim() -ne 'placed_requires_whole_design_review_no_route'){
        throw 'Unexpected placement completion state'
    }
    if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy; no competing run launched'}
    $checkpoint="$placement\physical_placed.dcp"
    $inputs=@{}
    foreach($p in @($checkpoint,$PSCommandPath,"$Root\route_dual_floorplan.tcl",
        "$bundle\continuation_tools\dual_cdc_preflight.tcl","$bundle\package\scripts\common.tcl",
        "$bundle\package\scripts\config.tcl","$bundle\package\scripts\run_support.tcl",
        "$bundle\package\scripts\constraint_checks.tcl")){
        $inputs[$p]=(Get-FileHash $p).Hash
    }
    $inputs | ConvertTo-Json | Set-Content "$Root\inputs.json"
    State 'placement_setup_gate_then_route'
    Push-Location $Root
    try {
        & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\route_dual_floorplan.tcl" -log "$Root\vivado.log" -tclargs $checkpoint "$bundle\package" "$bundle\continuation_tools" $Root
        $code=$LASTEXITCODE
    } finally {Pop-Location}
    foreach($p in $inputs.Keys){if((Get-FileHash $p).Hash -ne $inputs[$p]){throw "Input changed: $p"}}
    if($code -ne 0){throw "Routing or timing gate failed; inspect $Root\vivado.log"}
    State 'timing_closed_requires_drc_cdc_review_not_bitstream'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
}
