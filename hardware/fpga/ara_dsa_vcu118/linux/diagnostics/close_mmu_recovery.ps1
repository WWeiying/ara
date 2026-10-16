param([Parameter(Mandatory=$true)][string]$Tools)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$bundle='D:\fpga_runs\ara_mmu_fix_20261003'
$package="$bundle\package"
$checkpoint="$bundle\implementation_reviewed\ara_dsa_vcu118_routed.dcp"
$out="$bundle\recovery_closure"
if(Test-Path $out){throw 'Existing result: no automatic retry'}
if(@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count){throw 'Vivado busy'}
New-Item -ItemType Directory $out | Out-Null
$hashes=@{}
foreach($p in @($checkpoint,"$package\SHA256SUMS","$Tools\close_mmu_recovery.tcl",$PSCommandPath)){
    $hashes[$p]=(Get-FileHash $p).Hash
}
$hashes | ConvertTo-Json | Set-Content "$out\input_hashes.json"
function State($stage,$message=''){
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$false;HardwareValidated=$false;AutomaticProgramming=$false} |
      ConvertTo-Json | Set-Content "$out\state.json" -Encoding UTF8
}
function Verify {
    foreach($p in $hashes.Keys){
        if((Get-FileHash $p).Hash -ne $hashes[$p]){throw "Input changed: $p"}
    }
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
}
$lock=$null
$old=$env:ARA_FPGA_PROFILE
try {
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    Verify
    $env:ARA_FPGA_PROFILE='host_ethernet'
    State 'postroute_recovery_closure'
    Push-Location $out
    try {
        & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Tools\close_mmu_recovery.tcl" -log "$out\session.log" -tclargs $checkpoint $package $out
        if($LASTEXITCODE -ne 0){throw 'Recovery closure or strict gate failed'}
    } finally {Pop-Location}
    Verify
    if((Get-Content "$out\stage.txt" -Raw).Trim() -ne 'timing_passed_needs_full_audit'){
        throw 'Missing completion marker'
    }
    Get-FileHash "$out\candidate_routed.dcp" | ConvertTo-Json | Set-Content "$out\output_hash.json"
    State 'timing_passed_needs_full_audit'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally {
    $env:ARA_FPGA_PROFILE=$old
    if($null -ne $lock){$lock.Dispose()}
}
