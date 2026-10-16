# Continue the exact repaired synthesis; never resynthesize or program the board.
param([Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Review,
      [Parameter(Mandatory=$true)][string]$Out)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(Test-Path $Out){throw 'Continuation output exists; inspect checkpoints before resuming'}
New-Item -ItemType Directory $Out | Out-Null
$package="$Bundle\package"
$tools="$Bundle\tools"
$profile='dual_ddr_ethernet'
$reference='D:\fpga_runs\ara_mmu_fix_20261003\recovery_closure\candidate_routed.dcp'
$baseline='D:\fpga_runs\ara_mmu_fix_20261003\package\reports\synth_bd388cff3f8a\timing_gate.rpt'
$baselineCdc='D:\fpga_runs\ara_mmu_fix_20261003\release\package\reports\audit_1d7760b443eb\cdc.rpt'
$inventory=(Get-FileHash "$package\SHA256SUMS").Hash
$token=$inventory.Substring(0,12).ToLower()
$old=$env:ARA_FPGA_PROFILE
$lock=$null
$hashes=@{}
function State($stage,$message='') {
    $state=@{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      Profile=$profile;BoardModified=$false;AutomaticProgramming=$false;Output=$Out}
    $state | ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
    $state | ConvertTo-Json | Set-Content "$Bundle\state.json" -Encoding UTF8
}
function Verify {
    if((Get-FileHash "$package\SHA256SUMS").Hash -ne $inventory){throw 'Package inventory changed'}
    foreach($path in $hashes.Keys){
        if((Get-FileHash $path).Hash -ne $hashes[$path]){throw "Changed input: $path"}
    }
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
}
Start-Transcript -Path "$Out\flow.log" -NoClobber
try {
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    $env:ARA_FPGA_PROFILE=$profile
    State 'verify_reviewed_synthesis'
    Verify
    if((Get-Content "$Review\completed.txt" -Raw).Trim() -ne $token){throw 'Review/synthesis identity mismatch'}
    if((Get-FileHash $reference).Hash -ne '5A6B6873916B78148B97B1D5ABFE4B9CD547294667D4FBD7A41C2587EFE793FE'){throw 'Reference changed'}
    $original=Get-Content "$Bundle\input_hashes.json" -Raw | ConvertFrom-Json
    foreach($p in $original.PSObject.Properties){
        if((Get-FileHash $p.Name).Hash -ne $p.Value){throw "Original build input changed: $($p.Name)"}
    }
    $files=@($PSCommandPath,$reference,$baseline,$baselineCdc,"$tools\rebuild_mainrtl.tcl",
      "$PSScriptRoot\check_repaired_synthesis.py","$PSScriptRoot\check_rebuild_reports.py",
      "$PSScriptRoot\check_dual_synthesis.py",
      "$Bundle\runs\synthesis_timing.rpt","$package\SHA256SUMS",
      "$Bundle\c2_preflight_02\completed.txt","$Bundle\c2_preflight_02\c2_optimized.dcp")
    $files+=@(Get-ChildItem $Review -File | ForEach-Object FullName)
    foreach($path in $files){$hashes[$path]=(Get-FileHash $path).Hash}
    $hashes | ConvertTo-Json | Set-Content "$Out\input_hashes.json"
    & py -3 "$PSScriptRoot\check_repaired_synthesis.py" "$Bundle\runs\synthesis_timing.rpt" $baseline $Review "$Out\synthesis_gate.json"
    if($LASTEXITCODE -ne 0){throw 'Repaired physical review failed'}
    State 'incremental_implementation' 'Reusing repaired synthesis; all routed timing checks remain strict'
    & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -nojournal -source "$tools\rebuild_mainrtl.tcl" -log "$Out\implementation.log" -tclargs impl $package $Out $token "synth_$token" $reference
    if($LASTEXITCODE -ne 0){throw 'Implementation/routed gate failed; checkpoints retained'}
    Verify
    $lock.Dispose(); $lock=$null
    State 'routed_audit'
    $dcp="$Out\ara_dsa_vcu118_routed.dcp"
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\audit_routed.ps1" -Checkpoint $dcp -Profile $profile -RunRoot "$Out\audit"
    if($LASTEXITCODE -ne 0){throw 'Routed audit failed'}
    $manifests=@(Get-ChildItem "$Out\audit" -Recurse -Filter completed_audit.json)
    if($manifests.Count -ne 1){throw 'Missing/ambiguous audit'}
    $audit=Get-Content $manifests[0].FullName -Raw | ConvertFrom-Json
    if(!$audit.AutomatedChecksPassed -or $audit.SHA256 -ne (Get-FileHash $dcp).Hash){throw 'Audit identity mismatch'}
    State 'release_review'
    & py -3 "$PSScriptRoot\check_rebuild_reports.py" release $audit.Reports $baselineCdc --out "$Out\release_gate.json"
    if($LASTEXITCODE -ne 0){throw 'New CDC/DRC/timing finding requires review'}
    Verify
    State 'bitstream'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\write_profile_bit.ps1" -RunDir $Out -Profile $profile -Out "$Out\bitstream" -AuditManifest $manifests[0].FullName
    if($LASTEXITCODE -ne 0){throw 'Bitstream generation failed'}
    State 'bitstream_generated_not_programmed'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    $env:ARA_FPGA_PROFILE=$old
    Stop-Transcript
}
