# Audit the exact timing-closed checkpoint, then generate bit/probes. No programming.
param([Parameter(Mandatory=$true)][string]$Checker)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$b='D:\fpga_runs\ara_mmu_fix_20261003'
$source="$b\package"
$checkpoint="$b\recovery_closure\candidate_routed.dcp"
$expected='5A6B6873916B78148B97B1D5ABFE4B9CD547294667D4FBD7A41C2587EFE793FE'
$out="$b\release"
$prior='D:\fpga_runs\ara_mainrtl_finalize_20261001'
if(Test-Path $out){throw 'Existing release output; no restart'}
if((Get-FileHash $checkpoint).Hash -ne $expected){throw 'Wrong repaired checkpoint'}
if(@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count){throw 'Vivado busy'}
New-Item -ItemType Directory "$out\package" | Out-Null
Copy-Item "$prior\package\scripts" "$out\package" -Recurse
Copy-Item "$source\board_files" "$out\package" -Recurse
Copy-Item "$prior\package\reports\audit_cc1ab1094250\cdc.rpt" "$out\baseline_cdc.rpt"
Copy-Item $Checker "$out\check_rebuild_reports.py"
$tools="$out\package\scripts"
$hashes=@{}
foreach($f in @(Get-ChildItem "$out\package" -Recurse -File)){
    $hashes[$f.FullName]=(Get-FileHash $f.FullName).Hash
}
foreach($p in @($checkpoint,"$source\SHA256SUMS","$out\baseline_cdc.rpt","$out\check_rebuild_reports.py",$PSCommandPath)){
    $hashes[$p]=(Get-FileHash $p).Hash
}
$hashes | ConvertTo-Json -Depth 4 | Set-Content "$out\input_hashes.json"
function State($stage,$message=''){
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$false;HardwareValidated=$false;AutomaticProgramming=$false} |
      ConvertTo-Json | Set-Content "$out\state.json" -Encoding UTF8
}
function Verify {
    foreach($p in $hashes.Keys){
        if((Get-FileHash $p).Hash -ne $hashes[$p]){throw "Changed input: $p"}
    }
}
$handle=$null
try {
    State 'verify_inputs'
    & py -3 "$source\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Source package verification failed'}
    $handle=[IO.File]::Open($checkpoint,'Open','Read','Read')
    Verify
    State 'full_checkpoint_audit'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$tools\audit_routed.ps1" -Checkpoint $checkpoint -Profile host_ethernet -RunRoot "$out\audit"
    if($LASTEXITCODE -ne 0){throw 'Full audit failed; bitgen blocked'}
    Verify
    $manifests=@(Get-ChildItem "$out\audit" -Recurse -Filter completed_audit.json)
    if($manifests.Count -ne 1){throw 'Missing or ambiguous audit manifest'}
    $audit=Get-Content $manifests[0].FullName -Raw | ConvertFrom-Json
    if(!$audit.AutomatedChecksPassed -or $audit.Checkpoint -ne $checkpoint -or $audit.SHA256 -ne $expected){
        throw 'Audit not bound to repaired checkpoint'
    }
    State 'release_report_gate'
    & py -3 "$out\check_rebuild_reports.py" release $audit.Reports "$out\baseline_cdc.rpt" --out "$out\release_gate.json"
    if($LASTEXITCODE -ne 0){throw 'Timing/DRC/CDC comparison failed; bitgen blocked'}
    $skew=Join-Path $audit.Reports 'bus_skew.rpt'
    if(!(Test-Path $skew) -or !(Get-Item $skew).Length){throw 'Missing bus-skew evidence'}
    if(Select-String -LiteralPath $skew -SimpleMatch 'VIOLATED' -Quiet){throw 'Bus skew violation; bitgen blocked'}
    Verify
    State 'generating_bitstream' 'Experimental image; known baseline CDC findings still require manual review'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$tools\write_profile_bit.ps1" -RunDir "$b\recovery_closure" -Profile host_ethernet -Out "$out\bitstream_host_ethernet" -AuditManifest $manifests[0].FullName
    if($LASTEXITCODE -ne 0 -or !(Test-Path "$out\bitstream_host_ethernet\bitstream.json")){
        throw 'Bitstream generation failed'
    }
    Verify
    State 'bitstream_generated_not_programmed' 'Original Linux board acceptance remains required'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $handle){$handle.Dispose()}
}
