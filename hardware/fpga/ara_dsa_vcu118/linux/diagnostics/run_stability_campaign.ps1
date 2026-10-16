# Independent batches on the old single-DDR image; never use a new build image.
param([Parameter(Mandatory=$true)][string]$Out,
      [int]$ImplementationPid=23824)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(Test-Path $Out){throw 'New evidence directory required'}
$reference=Get-Content "$PSScriptRoot\reference_report.json" -Raw | ConvertFrom-Json
if(!$reference.passed -or @($reference.results).Count -lt 60){throw 'QEMU command reference incomplete'}
New-Item -ItemType Directory $Out | Out-Null
$results=@()
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;ProcessId=$PID;Updated=(Get-Date -Format o);
      Image='original_single_ddr_mmu_repaired';BoardModified=$true;
      NewBuildProgrammed=$false;Results=$results} | ConvertTo-Json -Depth 8 |
      Set-Content "$Out\state.json" -Encoding UTF8
}
Start-Transcript "$Out\flow.log"
try {
    $inputs=@{}
    foreach($file in Get-ChildItem $PSScriptRoot -File){$inputs[$file.FullName]=(Get-FileHash $file.FullName).Hash}
    $inputs | ConvertTo-Json | Set-Content "$Out\tool_hashes.json"
    foreach($profile in @('compute','storage','timers','process')) {
        foreach($file in $inputs.Keys){if((Get-FileHash $file).Hash -ne $inputs[$file]){throw 'Campaign tools changed'}}
        $phase="$Out\$profile"
        State "$profile/reload_original" 'Previous failure evidence saved before each fresh batch'
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\test_mmu_board.ps1" -Out $phase -ImplementationPids $ImplementationPid
        if($LASTEXITCODE -ne 0){throw "Boot/shell preparation failed: $profile"}
        State "$profile/testing"
        & py -3 "$PSScriptRoot\linux_stability.py" --profile $profile --repetitions 200 --out "$phase\matrix" --serial-wheel "$phase\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl"
        $testExit=$LASTEXITCODE
        if(!(Test-Path "$phase\matrix\report.json")){throw 'Missing matrix evidence'}
        $report=Get-Content "$phase\matrix\report.json" -Raw | ConvertFrom-Json
        $results+=@{Profile=$profile;Passed=$report.passed;ExitCode=$testExit;LastStage=$report.state;Report="$phase\matrix\report.json"}
        State "$profile/snapshot"
        & py -3 "$phase\tools\software\host_load.py" snapshot --probes 'D:\fpga_runs\ara_mmu_fix_20261003\release\bitstream_host_ethernet\ara_dsa_vcu118.ltx' --vivado 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' --out "$phase\after_matrix"
        $snapshotExit=$LASTEXITCODE
        if(!(Test-Path "$phase\after_matrix\snapshot.json")){throw 'No snapshot: preserve board and stop'}
        $snapshot=Get-Content "$phase\after_matrix\snapshot.json" -Raw | ConvertFrom-Json
        if($snapshot.identity.magic -ne 1095910466 -or $snapshot.identity.caps -ne 1){throw 'Snapshot identity mismatch'}
        $results[-1].SnapshotExit=$snapshotExit
        $results[-1].DdrErrors=$snapshot.ddr1.error_count
        $results[-1].Snapshot="$phase\after_matrix\snapshot.json"
        # An acquisition cleanup failure must be visible even if the data exists.
        $results[-1].BatchPassed=($report.passed -and $testExit -eq 0 -and $snapshotExit -eq 0 -and $snapshot.ddr1.error_count -eq 0)
        State "$profile/recorded"
    }
    $failures=@($results | Where-Object {!$_.BatchPassed})
    if($failures.Count){State 'completed_with_failures' 'No blanket stability acceptance; inspect each batch'}
    else{State 'bounded_campaign_passed' 'Not full ISA, full physical RAM or long-duration acceptance'}
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {Stop-Transcript}
