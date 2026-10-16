param([Parameter(Mandatory=$true)][string]$Root)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$bundle='D:\fpga_runs\ara_dual_inval_clock_fix_20261004'
$checkpoint="$bundle\implementation_reviewed_01\ara_dsa_vcu118_routed.dcp"
$out="$Root\review_01"
if(Test-Path $out){throw 'Review exists; do not restart'}
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
$hashes=@{}
foreach($p in @($checkpoint,"$bundle\package\SHA256SUMS","$Root\cdc.xdc",
               "$Root\review_dual_constraint_loss.tcl",$PSCommandPath)){
    $hashes[$p]=(Get-FileHash $p).Hash
}
$hashes | ConvertTo-Json | Set-Content "$Root\input_hashes.json"
function State($stage,$message=''){
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$false;AutomaticProgramming=$false;Output=$out} |
      ConvertTo-Json | Set-Content "$Root\state.json" -Encoding UTF8
}
Start-Transcript -Path "$Root\review_flow.log" -NoClobber
try {
    State 'reviewing_preserved_checkpoint'
    Push-Location $Root
    try {
        & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\review_dual_constraint_loss.tcl" -log "$Root\review.log" -tclargs $checkpoint "$bundle\package" "$Root\cdc.xdc" $out
        if($LASTEXITCODE -ne 0){throw 'Constraint review failed; inspect logs'}
    } finally {Pop-Location}
    foreach($p in $hashes.Keys){
        if((Get-FileHash $p).Hash -ne $hashes[$p]){throw "Input changed: $p"}
    }
    State 'reviewed_not_timing_or_hardware_acceptance'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally {Stop-Transcript}
