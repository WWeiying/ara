# Detached, offline sequence: C2 legality first, then the full repaired build.
param([Parameter(Mandatory=$true)][string]$Bundle,
      [ValidatePattern('^c2_preflight(_[0-9]+)?$')][string]$Preflight='c2_preflight')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Bundle=(Resolve-Path $Bundle).Path
$tools="$Bundle\tools"
$xci='D:\fpga_runs\ara_dual_ethernet_20261004\package\build\ara_dsa_vcu118_dual_ddr_ethernet\ara_dsa_vcu118_dual_ddr_ethernet.srcs\sources_1\ip\ddr4_c2\ddr4_c2.xci'
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      Profile='dual_ddr_ethernet';BoardModified=$false;AutomaticProgramming=$false} |
        ConvertTo-Json | Set-Content "$Bundle\state.json" -Encoding UTF8
}
Start-Transcript -Path "$Bundle\repair_flow_$Preflight.log" -NoClobber
try {
    State 'verify_repair'
    & py -3 "$Bundle\package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Repair package verification failed'}
    $regressions=@(Get-ChildItem "$Bundle\tests" -Recurse -Filter results.json)
    if($regressions.Count -lt 4){throw 'Missing repair regressions'}
    foreach($file in $regressions) {
        $results=@(Get-Content $file.FullName -Raw | ConvertFrom-Json)
        if(!$results.Count -or @($results | Where-Object { !$_.passed }).Count){throw "Regression failed: $file"}
    }
    $hash=(Get-FileHash $xci).Hash
    State 'c2_clock_preflight' 'Offline isolated MIG optimization; no board access'
    & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -nojournal -source "$tools\c2_clock_preflight.tcl" -log "$Bundle\$Preflight.log" -tclargs $xci "$Bundle\package" "$Bundle\$Preflight"
    if($LASTEXITCODE -ne 0 -or !(Test-Path "$Bundle\$Preflight\completed.txt")){throw 'C2 MIG clock legality failed'}
    if((Get-FileHash $xci).Hash -ne $hash){throw 'Original MIG configuration changed'}
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$tools\build_dual_ethernet.ps1" -Bundle $Bundle
    if($LASTEXITCODE -ne 0){throw 'Full repair build stopped; see flow.log and stage reports'}
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally { Stop-Transcript }
