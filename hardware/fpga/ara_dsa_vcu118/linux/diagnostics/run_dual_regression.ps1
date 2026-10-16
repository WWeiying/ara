param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$board='D:\fpga_runs\ara_dual_board_20261006_01'
$software='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package\software'
$probes='D:\fpga_runs\ara_dual_bitgen_20261006_01\bitstream\ara_dsa_vcu118.ltx'
$results=@()
$lock=$null
function State($stage,$message='') {
 @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);Results=$script:results;
   Profile='dual_ddr_ethernet';ResetPerformed=$false;PlannedGroups=73;
   LinuxMemoryScope='Original single-bank device tree';ExtendedSuite='Not included in this 73-group regression'} |
   ConvertTo-Json -Depth 8 | Set-Content "$Out\state.json"
}
function Snapshot($destination) {
 & py -3 "$software\host_load.py" snapshot --probes $probes --out $destination --vivado D:\Xilinx\Vivado\2020.1\bin\vivado.bat | Out-Host
 if($LASTEXITCODE){throw 'Snapshot failed; preserve board'}
 $s=Get-Content "$destination\snapshot.json" -Raw | ConvertFrom-Json
 if($s.identity.caps -ne 3 -or $s.ddr1.error_count -ne 0 -or $s.ddr2.error_count -ne 0){throw 'Dual DDR identity/errors failed'}
}
Start-Transcript "$Out\console.log" -NoClobber
try {
 $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
 if(@(Get-Process vivado,python,xsct -ErrorAction SilentlyContinue).Count){throw 'Other test clients running'}
 $hashes=@{}
 foreach($f in Get-ChildItem "$Out\tools" -File){$hashes[$f.FullName]=(Get-FileHash $f.FullName).Hash}
 $hashes | ConvertTo-Json | Set-Content "$Out\inputs.json"
 State 'preflight'
 Snapshot "$Out\before"
 foreach($profile in @('process','compute','storage','timers','shell_copy')) {
  foreach($p in $hashes.Keys){if((Get-FileHash $p).Hash -ne $hashes[$p]){throw 'Test tools changed'}}
  State "$profile/testing"
  Write-Host "=== $profile : current dual-DDR bitstream, no reprogramming ===" -ForegroundColor Cyan
  if($profile -eq 'shell_copy') {
   & py -3 "$Out\tools\check_linux_console.py" --port COM6 --out "$Out\$profile" --seconds 120 --tx-gap 0.02 --serial-wheel "$board\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl" | Out-Host
  } else {
   & py -3 "$Out\tools\linux_stability.py" --profile $profile --repetitions 200 --out "$Out\$profile" --serial-wheel "$board\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl" | Out-Host
  }
  $code=$LASTEXITCODE
  $r=Get-Content "$Out\$profile\report.json" -Raw | ConvertFrom-Json
  $script:results+=@{Profile=$profile;Passed=($code -eq 0 -and $r.passed);ExitCode=$code;Report="$Out\$profile\report.json"}
  State "$profile/snapshot"
  Snapshot "$Out\after_$profile"
  if($code -ne 0 -or !$r.passed){throw "Failed $profile; board preserved, later groups not run"}
 }
 State 'bounded_regression_passed' '73 groups; extended stress/RVV and dual-bank Linux allocation not covered'
 Write-Host 'REGRESSION PASSED' -ForegroundColor Green
} catch {
 State 'stopped_for_review' ($_ | Out-String)
 Write-Host ($_ | Out-String) -ForegroundColor Red
} finally {
 if($null -ne $lock){$lock.Dispose()}
 Stop-Transcript
}
