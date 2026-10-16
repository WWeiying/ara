# Reuse the completed synthesis; no source/XDC changes and no board access.
param([Parameter(Mandatory=$true)][string]$Tools)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$bundle='D:\fpga_runs\ara_mmu_fix_20261003'
$package="$bundle\package"
$out="$bundle\implementation_reviewed"
$token='bd388cff3f8a'
$synth="$bundle\runs\ara_20261003_132113_bd388cff3f8a\synth_bd388cff3f8a\ara_dsa_vcu118.dcp"
$reference='D:\fpga_runs\ara_mainrtl_finalize_20261001\runs\ara_dsa_vcu118_routed.dcp'
$baseline='D:\fpga_runs\ara_mainrtl_20260930\runs\synthesis_timing.rpt'
$current="$package\reports\synth_$token\timing_gate.rpt"
if(Test-Path $out){throw 'Output exists; inspect it instead of restarting'}
if(@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count){throw 'Vivado busy'}
if((Get-FileHash $reference).Hash -ne '7884B794A6C41DE283C5E4AF00202E6268704CF70136FA7A3D09A33A58A16D8E'){
    throw 'Physical reference hash mismatch'
}
New-Item -ItemType Directory $out | Out-Null
$hashes=@{}
foreach($p in @($synth,$reference,$baseline,$current,"$package\SHA256SUMS",
               "$Tools\check_rebuild_reports.py","$Tools\rebuild_mainrtl.tcl",
               "$Tools\export_mmu_repair.tcl",$PSCommandPath)){
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
        if((Get-FileHash $p).Hash -ne $hashes[$p]){throw "Changed input: $p"}
    }
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
}
$lock=$null
$old=$env:ARA_FPGA_PROFILE
try {
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    Verify
    State 'review_synthesis_physical_groups'
    & py -3 "$Tools\check_rebuild_reports.py" synthesis $current $baseline --out "$out\synthesis_gate.json"
    if($LASTEXITCODE -ne 0){throw 'Synthesis comparison failed'}
    $env:ARA_FPGA_PROFILE='host_ethernet'
    State 'export_repaired_mmu_netlist'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Tools\export_mmu_repair.tcl" -log "$out\export.log" -tclargs $package $synth "$out\netlist"
    if($LASTEXITCODE -ne 0){throw 'Netlist export failed'}
    Verify
    State 'incremental_implementation' 'No synthesis rerun; strict routed gate retained; mapped MMU functional audit pending'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Tools\rebuild_mainrtl.tcl" -log "$out\implementation.log" -tclargs impl $package $out $token "synth_$token" $reference
    if($LASTEXITCODE -ne 0){throw 'Implementation or routed timing failed'}
    Verify
    if((Get-Content "$out\stage.txt" -Raw).Trim() -ne 'routed_ready_for_audit'){throw 'Missing completion marker'}
    State 'routed_ready_for_audit' 'MMU netlist, DRC, CDC and original Linux board acceptance remain required'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally {
    $env:ARA_FPGA_PROFILE=$old
    if($null -ne $lock){$lock.Dispose()}
}
