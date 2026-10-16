param([Parameter(Mandatory=$true)][string]$Root)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$bundle='D:\fpga_runs\ara_dual_inval_clock_fix_20261004'
$package="$bundle\package"
$out="$Root\implementation"
if(Test-Path $out){throw 'Existing implementation; inspect before retrying'}
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
New-Item -ItemType Directory $out | Out-Null
$hashes=@{}
foreach($f in @(Get-ChildItem "$Root\tools" -File)){$hashes[$f.FullName]=(Get-FileHash $f.FullName).Hash}
foreach($f in @(Get-ChildItem "$package\build" -Recurse -Filter *.dcp)){$hashes[$f.FullName]=(Get-FileHash $f.FullName).Hash}
foreach($p in @("$bundle\runs\synth_903503b5ace4\ara_dsa_vcu118.dcp","$package\SHA256SUMS",$PSCommandPath)){
    $hashes[$p]=(Get-FileHash $p).Hash
}
$hashes | ConvertTo-Json | Set-Content "$Root\input_hashes.json"
$token=(Get-FileHash "$Root\tools\cdc.xdc").Hash.Substring(0,12).ToLower()
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      Profile='dual_ddr_ethernet';BoardModified=$false;AutomaticProgramming=$false;Output=$out} |
      ConvertTo-Json | Set-Content "$Root\state.json" -Encoding UTF8
}
function Verify {
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Sealed package verification failed'}
    foreach($p in $hashes.Keys){if((Get-FileHash $p).Hash -ne $hashes[$p]){throw "Input changed: $p"}}
}
$lock=$null
Start-Transcript -Path "$Root\flow.log" -NoClobber
try {
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    State 'verifying_inputs'
    Verify
    Copy-Item "$package\build\ara_dsa_vcu118_dual_ddr_ethernet\ara_dsa_vcu118_dual_ddr_ethernet.xpr" "$Root\original_project.xpr"
    State 'implementation_with_corrected_constraints'
    Push-Location $Root
    try {
        & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\tools\rebuild_dual_cdc.tcl" -log "$Root\implementation.log" -tclargs $bundle "$Root\tools" $out $token
        if($LASTEXITCODE -ne 0){throw 'Implementation stopped; inspect retained reports/checkpoints'}
    } finally {Pop-Location}
    Verify
    State 'routed_ready_for_full_audit' 'Strict timing/skew passed; full CDC/DRC audit and bitgen still required'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    Stop-Transcript
}
