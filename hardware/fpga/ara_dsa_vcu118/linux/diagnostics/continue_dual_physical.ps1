# Physical trial of the frozen dual-DDR synthesis. No RTL changes or board access.
param([Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Review,
      [Parameter(Mandatory=$true)][string]$Out)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(Test-Path $Out){throw 'Physical trial exists; inspect before any resume'}
New-Item -ItemType Directory $Out | Out-Null
$package="$Bundle\package"
$reference='D:\fpga_runs\ara_mmu_fix_20261003\recovery_closure\candidate_routed.dcp'
$baseline='D:\fpga_runs\ara_mmu_fix_20261003\package\reports\synth_bd388cff3f8a\timing_gate.rpt'
$env:ARA_FPGA_PROFILE='dual_ddr_ethernet'
$lock=$null
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$false;AutomaticProgramming=$false;Output=$Out} |
        ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
}
Start-Transcript -Path "$Out\console.log" -NoClobber
try {
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    State 'verify_frozen_inputs'
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
    if((Get-FileHash $reference).Hash -ne '5A6B6873916B78148B97B1D5ABFE4B9CD547294667D4FBD7A41C2587EFE793FE') {throw 'Reference changed'}
    $original=Get-Content "$Bundle\input_hashes.json" -Raw | ConvertFrom-Json
    foreach($property in $original.PSObject.Properties) {
        if((Get-FileHash -LiteralPath $property.Name).Hash -ne $property.Value){throw "Original input changed: $($property.Name)"}
    }
    State 'review_synthesis_estimates'
    & py -3 "$PSScriptRoot\check_dual_synthesis.py" "$Bundle\runs\synthesis_timing.rpt" $baseline "$Out\synthesis_review.json" --physical-review $Review
    if($LASTEXITCODE -ne 0){throw 'Physical trial not authorized by scoped review'}
    $files=@($PSCommandPath,"$PSScriptRoot\check_dual_synthesis.py","$PSScriptRoot\check_rebuild_reports.py",
       "$Bundle\tools\rebuild_mainrtl.tcl","$Bundle\runs\synthesis_timing.rpt",$baseline,$reference,
       "$Review\clocks.tsv","$Review\paths.tsv","$Review\review_complete.txt","$package\SHA256SUMS")
    $hashes=@{}
    foreach($file in $files){$hashes[$file]=(Get-FileHash $file).Hash}
    $hashes | ConvertTo-Json | Set-Content "$Out\input_hashes.json"
    State 'physical_implementation_trial' 'C2 estimates reviewed, not waived; routed timing must pass'
    & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -nojournal -source "$Bundle\tools\rebuild_mainrtl.tcl" -log "$Out\implementation.log" -tclargs impl $package $Out debfe7e4727b synth_debfe7e4727b $reference
    if($LASTEXITCODE -ne 0){throw 'Implementation or strict routed gate failed; checkpoints retained'}
    foreach($file in $hashes.Keys){if((Get-FileHash $file).Hash -ne $hashes[$file]){throw "Input changed: $file"}}
    State 'routed_ready_for_audit' 'Not a bitstream acceptance; CDC/DRC and functional defect review remain'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    Stop-Transcript
}
