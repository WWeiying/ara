param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Checkpoint)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$bundle='D:\fpga_runs\ara_dual_reset_locality_20261005_01'
function State($name,$message='') {
    @{Stage=$name;Message=$message;Updated=(Get-Date -Format o);BoardModified=$false} |
        ConvertTo-Json | Set-Content "$Root\state.json" -Encoding UTF8
}
try {
    if(Test-Path "$Root\inputs.json"){throw 'Output already used'}
    if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
    $inputs=@{}
    foreach($p in @($Checkpoint,$PSCommandPath,"$Root\route_dual_floorplan.tcl",
        "$bundle\continuation_tools\dual_cdc_preflight.tcl","$bundle\package\scripts\common.tcl",
        "$bundle\package\scripts\config.tcl","$bundle\package\scripts\run_support.tcl",
        "$bundle\package\scripts\constraint_checks.tcl")) {
        $inputs[$p]=(Get-FileHash $p).Hash
    }
    $inputs | ConvertTo-Json | Set-Content "$Root\inputs.json"
    State 'resume_routed_checkpoint_for_signoff'
    Push-Location $Root
    try {
        & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\route_dual_floorplan.tcl" -log "$Root\vivado.log" -tclargs $Checkpoint "$bundle\package" "$bundle\continuation_tools" $Root routed
        $code=$LASTEXITCODE
    } finally {Pop-Location}
    foreach($p in $inputs.Keys){if((Get-FileHash $p).Hash -ne $inputs[$p]){throw "Input changed: $p"}}
    if($code -ne 0){throw "Vivado gates failed: exit $code"}
    State 'timing_closed_requires_drc_cdc_review_not_bitstream'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
}
