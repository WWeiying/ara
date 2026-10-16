# Offline build only: no hardware manager, reset, programming or UART access.
param([Parameter(Mandatory=$true)][string]$Bundle)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Bundle=(Resolve-Path $Bundle).Path
$package="$Bundle\package"
$tools="$Bundle\tools"
$profile='dual_ddr_ethernet'
$vivado='D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
$reference='D:\fpga_runs\ara_mmu_fix_20261003\recovery_closure\candidate_routed.dcp'
$referenceHash='5A6B6873916B78148B97B1D5ABFE4B9CD547294667D4FBD7A41C2587EFE793FE'
$baseline='D:\fpga_runs\ara_mmu_fix_20261003\package\reports\synth_bd388cff3f8a\timing_gate.rpt'
$baselineCdc='D:\fpga_runs\ara_mmu_fix_20261003\release\package\reports\audit_1d7760b443eb\cdc.rpt'
$out="$Bundle\runs"
if(Test-Path $out){throw 'Run exists; inspect/reuse checkpoints instead of restarting'}
New-Item -ItemType Directory $out | Out-Null
$inventory=(Get-FileHash "$package\SHA256SUMS").Hash
$token=$inventory.Substring(0,12).ToLower()
$old=$env:ARA_FPGA_PROFILE
$lock=$null
$hashes=@{}
function State($stage,$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      Profile=$profile; BoardModified=$false; AutomaticProgramming=$false} |
      ConvertTo-Json | Set-Content "$Bundle\state.json" -Encoding UTF8
}
function Verify {
    if((Get-FileHash "$package\SHA256SUMS").Hash -ne $inventory){throw 'Inventory changed'}
    if((Get-FileHash $reference).Hash -ne $referenceHash){throw 'Reference changed'}
    foreach($p in $hashes.Keys){
        if((Get-FileHash $p).Hash -ne $hashes[$p]){throw "Changed build input: $p"}
    }
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
}
Start-Transcript -Path "$Bundle\flow.log" -NoClobber
try {
    State 'verify_inputs'
    Verify
    $hashes=@{}
    foreach($p in @($reference,$baseline,$baselineCdc,$PSCommandPath) + @(Get-ChildItem $tools -File | ForEach-Object FullName)){
        $hashes[$p]=(Get-FileHash $p).Hash
    }
    $hashes | ConvertTo-Json | Set-Content "$Bundle\input_hashes.json"
    State 'prepare_ip' 'Serial OOC jobs to limit memory use; board untouched'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\create_profile.ps1" -Profile $profile
    if($LASTEXITCODE -ne 0){throw 'IP preparation failed'}
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    $env:ARA_FPGA_PROFILE=$profile
    Verify
    State 'synthesis'
    & $vivado -mode batch -notrace -nojournal -source "$tools\rebuild_mainrtl.tcl" -log "$out\synthesis.log" -tclargs synth $package $out $token - $reference
    if($LASTEXITCODE -ne 0){throw 'Synthesis/structural/setup checks failed'}
    State 'synthesis_physical_review'
    & py -3 "$tools\check_dual_synthesis.py" "$out\synthesis_timing.rpt" $baseline "$out\synthesis_gate.json"
    if($LASTEXITCODE -ne 0){throw 'New/worse synthesis physical finding requires review'}
    Verify
    State 'incremental_implementation' 'Reuse placement only; current dual-channel netlist remains authoritative'
    & $vivado -mode batch -notrace -nojournal -source "$tools\rebuild_mainrtl.tcl" -log "$out\implementation.log" -tclargs impl $package $out $token "synth_$token" $reference
    if($LASTEXITCODE -ne 0){throw 'Implementation/routed gate failed; checkpoint preserved'}
    Verify
    $lock.Dispose(); $lock=$null
    State 'routed_audit'
    $dcp="$out\ara_dsa_vcu118_routed.dcp"
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\audit_routed.ps1" -Checkpoint $dcp -Profile $profile -RunRoot "$Bundle\audit"
    if($LASTEXITCODE -ne 0){throw 'Routed audit failed'}
    $manifests=@(Get-ChildItem "$Bundle\audit" -Recurse -Filter completed_audit.json)
    if($manifests.Count -ne 1){throw 'Ambiguous/missing audit'}
    $audit=Get-Content $manifests[0].FullName -Raw | ConvertFrom-Json
    if(!$audit.AutomatedChecksPassed -or $audit.SHA256 -ne (Get-FileHash $dcp).Hash){throw 'Audit identity mismatch'}
    State 'release_review' 'New C2 CDC paths must be reviewed; not automatically waived'
    & py -3 "$tools\check_rebuild_reports.py" release $audit.Reports $baselineCdc --out "$out\release_gate.json"
    if($LASTEXITCODE -ne 0){throw 'New CDC/DRC/timing finding requires review; no bitstream accepted'}
    Verify
    State 'bitstream'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\write_profile_bit.ps1" -RunDir $out -Profile $profile -Out "$Bundle\bitstream" -AuditManifest $manifests[0].FullName
    if($LASTEXITCODE -ne 0){throw 'Bitstream generation failed'}
    State 'bitstream_generated_not_programmed' 'Board remains on the original single-DDR Linux image'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    $env:ARA_FPGA_PROFILE=$old
    Stop-Transcript
}
