param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$board='D:\fpga_runs\ara_dual_board_20261006_01'
$software='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package\software'
$probes='D:\fpga_runs\ara_dual_bitgen_20261006_01\bitstream\ara_dsa_vcu118.ltx'
$wheel="$board\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl"
$results=@(); $boots=0; $bootFailures=0; $lock=$null
function State($stage,$message='') {
 @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);Results=$script:results;
   Planned=73;ReprogramAttempts=$script:boots;LinuxMemoryScope='Original single-bank device tree';
   Scope='Independent original targets plus separately counted fixtures, not continuous soak';
   PriorFailure='D:\fpga_runs\ara_dual_regression_20261006_01\process'} |
   ConvertTo-Json -Depth 8 | Set-Content "$Out\state.json"
}
function Snapshot($path) {
 & py -3 "$software\host_load.py" snapshot --probes $probes --out $path --vivado D:\Xilinx\Vivado\2020.1\bin\vivado.bat | Out-Host
 if($LASTEXITCODE -ne 0){return $false}
 $s=Get-Content "$path\snapshot.json" -Raw | ConvertFrom-Json
 return ($s.identity.caps -eq 3 -and $s.ddr1.error_count -eq 0 -and $s.ddr2.error_count -eq 0)
}
Start-Transcript "$Out\console.log" -NoClobber
try {
 $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
 if(@(Get-Process vivado,python,xsct -ErrorAction SilentlyContinue).Count){throw 'Board clients busy'}
 $inventory=@(Get-ChildItem "$Out\tools" -File | Get-FileHash)
 $inventory | ConvertTo-Json | Set-Content "$Out\tool_hashes.json"
 $plan=Get-Content "$Out\plan.json" -Raw | ConvertFrom-Json
 if(@($plan).Count -ne 73){throw 'Expected 73 targets'}
 State 'preserve_then_check_shell'
 $null=Snapshot "$Out\before_recovery"
 & py -3 "$Out\tools\check_linux_console.py" --port COM6 --out "$Out\recovery_probe" --seconds 30 --tx-gap 0.02 --clear-line --serial-wheel $wheel | Out-Host
 $ready=($LASTEXITCODE -eq 0)
 foreach($case in $plan) {
  $name="$($case.profile)_$($case.name)"
  foreach($h in $inventory){if((Get-FileHash $h.Path).Hash -ne $h.Hash){throw 'Tools changed during campaign'}}
  if(!$ready -and $bootFailures -lt 2) {
   $boots++
   $boot="$Out\boot_$boots"
   New-Item -ItemType Directory $boot | Out-Null
   Copy-Item "$board\tools" "$boot\tools" -Recurse
   Copy-Item "$board\program_host_image.tcl" $boot
   State "$name/recover_same_image"
   & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Out\tools\boot_dual_original.ps1" -Out $boot | Out-Host
   $ready=($LASTEXITCODE -eq 0)
   if($ready){$bootFailures=0}else{$bootFailures++}
  }
  if(!$ready) {
   $results+=@{Profile=$case.profile;Name=$case.name;Status='not_run_recovery_failed';Passed=$false;Boot=$boots}
   State "$name/unavailable" 'Recovery failed; not counted as a test failure or pass'
   continue
  }
  State "$name/testing"
  Write-Host "=== $name ===" -ForegroundColor Cyan
  if($case.profile -eq 'shell') {
   & py -3 "$Out\tools\check_linux_console.py" --port COM6 --out "$Out\$name" --seconds 120 --tx-gap 0.02 --serial-wheel $wheel | Out-Host
  } else {
   & py -3 "$Out\tools\linux_stability.py" --profile $case.profile --matrix-case $case.name --repetitions 200 --out "$Out\$name" --serial-wheel $wheel | Out-Host
  }
  $code=$LASTEXITCODE
  $record=@{Profile=$case.profile;Name=$case.name;Passed=$false;Status='missing_report';Boot=$boots;ExitCode=$code;Report="$Out\$name\report.json"}
  if(Test-Path $record.Report) {
   $r=Get-Content $record.Report -Raw | ConvertFrom-Json
   if($case.profile -eq 'shell'){$started=$r.command_sent; $targetPass=$r.passed}
   else {
    $target=@($r.results | Where-Object {$_.name -eq $case.name})
    $started=$target.Count -eq 1
    $targetPass=$started -and $target[0].passed
   }
   $record.TargetPassed=[bool]$targetPass
   $record.Passed=($code -eq 0 -and $r.passed -and $targetPass)
   $record.Status=if($record.Passed){'passed'}elseif(!$started){'not_run_fixture_or_connection_failed'}else{'failed'}
  }
  $results+=,$record
  State "$name/recorded"
  $ready=$record.Passed
  if(!$ready) {
   $healthy=Snapshot "$Out\snapshot_$name"
   $record.SnapshotHealthy=$healthy
   State "$name/failed_continuing" 'Evidence saved; next target will get a fresh boot'
  }
 }
 $null=Snapshot "$Out\final_snapshot"
 if(@($results | Where-Object {!$_.Passed}).Count){State 'completed_with_failures_or_gaps'}
 else {State 'all_73_isolated_targets_passed' 'Does not erase the prior continuous pipes timeout'}
 Write-Host "Completed campaign: $Out" -ForegroundColor Cyan
} catch {
 State 'infrastructure_failure' ($_ | Out-String)
 Write-Host ($_ | Out-String) -ForegroundColor Red
} finally {
 if($null -ne $lock){$lock.Dispose()}
 Stop-Transcript
}
