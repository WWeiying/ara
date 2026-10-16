# Never takes COM6/JTAG until the predecessor is terminal and the board lock is free.
param([string]$QueueOut,
      [string]$Predecessor='D:\fpga_runs\ara_independent_stability_20261005_01',
      [string]$PredecessorTask='AraIndependentStability20261005',
      [int[]]$AllowedVivadoPids=@(),
      [switch]$RestartConfirmed,
      [switch]$LibraryOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$asLibrary=$LibraryOnly
$approved=$RestartConfirmed
. "$PSScriptRoot\run_independent_stability.ps1" -LibraryOnly

function Assert-Predecessor($previous) {
    if($previous.Stage -notin @('bounded_campaign_passed','completed_with_failures')){
        throw 'Predecessor did not finish safely; preserve its board scene'
    }
    if(@($previous.Results).Count -ne 5){throw 'Incomplete predecessor inventory'}
    $expected=@('compute','storage','timers','process','shell_copy')
    for($i=0;$i -lt 5;$i++){
        $r=$previous.Results[$i]
        if($r.Profile -ne $expected[$i] -or $r.SnapshotExit -ne 0 -or $r.DdrErrors -ne 0){
            throw 'Incomplete/unsafe predecessor evidence; no reset'
        }
        foreach($p in @($r.Report,$r.Snapshot)){if(!(Test-Path -LiteralPath $p)){throw 'Missing predecessor evidence'}}
    }
}
function Get-QueueDisposition($taskState,$previous) {
    if($taskState -in @('Running','Queued')){return 'waiting_for_existing_campaign'}
    if($previous.Stage -eq 'stopped_for_review'){return 'held_for_predecessor_review'}
    Assert-Predecessor $previous
    return 'ready'
}
function Get-ExtendedVerdict($report,$code,$captured) {
    Assert-SingleDdrSnapshot $captured.Data
    $n=@($report.planned).Count
    $done=@($report.results).Count
    $good=@($report.results | Where-Object {$_.passed}).Count
    return ($n -gt 0 -and $n -eq $done -and $good -eq $n -and
            $report.passed -and $code -eq 0 -and $captured.Code -eq 0 -and
            $captured.Data.ddr1.error_count -eq 0)
}
if($asLibrary){return}
if(!$approved){throw 'Archive/reset approval required'}
if(!$QueueOut -or (Test-Path $QueueOut)){throw 'New queue directory required'}
New-Item -ItemType Directory $QueueOut | Out-Null
$script:results=@()
$script:modified=$false
function Queue-State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$script:modified;NewBuildProgrammed=$false;
      Image='original_single_ddr_bit_kernel_with_opt_test_tools';Results=$script:results;
      Predecessor=$Predecessor;Deferred=(Get-Content "$PSScriptRoot\coverage.json" -Raw | ConvertFrom-Json)} |
      ConvertTo-Json -Depth 12 | Set-Content "$QueueOut\state.tmp" -Encoding UTF8
    Move-Item "$QueueOut\state.tmp" "$QueueOut\state.json" -Force
}
function Verify-FrozenSuite {
    $inventory=Get-Content "$PSScriptRoot\frozen.json" -Raw | ConvertFrom-Json
    foreach($f in $inventory){
        if((Get-FileHash (Join-Path $PSScriptRoot $f.Path)).Hash -ne $f.SHA256){throw "Frozen suite changed: $($f.Path)"}
    }
    $ref=Get-Content "$PSScriptRoot\reference_report.json" -Raw | ConvertFrom-Json
    if(!$ref.passed -or !$ref.reduced_reference_load){throw 'Missing extended QEMU reference pass'}
    foreach($file in $ref.tool_hashes.PSObject.Properties){
        if((Get-FileHash (Join-Path $PSScriptRoot $file.Name)).Hash -ne $file.Value){throw 'Reference tools changed'}
    }
}
function Invoke-ExtendedBatch($name,$profile) {
    Verify-FrozenSuite
    $phase=Join-Path $QueueOut $name
    Queue-State "$name/boot"
    $script:modified=$true
    $command="& '$PSScriptRoot\test_mmu_board.ps1' -Out '$phase' -BootOnly -TestSuiteDir '$PSScriptRoot'"
    if(@($AllowedVivadoPids).Count){$command+=' -ImplementationPids @('+($AllowedVivadoPids -join ',')+')'}
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded | Out-Host
    if($LASTEXITCODE){throw "Boot/transport failure in $name; no further resets"}
    Queue-State "$name/testing"
    & py -3 "$PSScriptRoot\linux_stability.py" --extended-profile $profile --out "$phase\matrix" --serial-wheel "$phase\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl" | Out-Host
    $code=$LASTEXITCODE
    if(!(Test-Path "$phase\matrix\report.json")){throw 'Missing workload report; preserve board'}
    $report=Get-Content "$phase\matrix\report.json" -Raw | ConvertFrom-Json
    Queue-State "$name/snapshot"
    $snap=Save-BoardSnapshot "$phase\tools\software" "$phase\after_matrix"
    $pass=Get-ExtendedVerdict $report $code $snap
    $script:results+=@{Name=$name;Profile=$profile;Passed=$pass;Counts=$report.counts;
                        ExitCode=$code;Report="$phase\matrix\report.json";Snapshot=$snap.Path}
    Queue-State "$name/recorded" 'Workload evidence preserved before any subsequent reset'
    if($snap.Code -ne 0 -or $snap.Data.ddr1.error_count -ne 0){throw 'Hardware snapshot error; no more resets'}
}
$lock=$null
Start-Transcript "$QueueOut\flow.log"
try {
    Verify-FrozenSuite
    $deadline=(Get-Date).AddHours(48)
    while($true){
        $task=Get-ScheduledTask -TaskName $PredecessorTask
        $previous=$null
        if($task.State -notin @('Running','Queued')){
            $previous=Get-Content "$Predecessor\state.json" -Raw | ConvertFrom-Json
        }
        $disposition=Get-QueueDisposition $task.State $previous
        if($disposition -eq 'ready'){break}
        Queue-State $disposition 'No COM6/JTAG/reset; predecessor must finish and retain complete evidence before continuation'
        if((Get-Date) -gt $deadline){throw 'Predecessor wait exceeded 48 hours; nothing reset'}
        Start-Sleep -Seconds 60
    }
    $previous=Get-Content "$Predecessor\state.json" -Raw | ConvertFrom-Json
    Assert-Predecessor $previous
    $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
    if((Get-ScheduledTask -TaskName $PredecessorTask).State -in @('Running','Queued')){throw 'Predecessor restarted; no reset'}
    Queue-State 'archiving_predecessor'
    Copy-Item "$Predecessor\state.json" "$QueueOut\predecessor.json"
    foreach($r in $previous.Results){
        $dir="$QueueOut\preserved\$($r.Profile)"
        New-Item -ItemType Directory $dir -Force | Out-Null
        Copy-Item (Split-Path $r.Report) "$dir\matrix" -Recurse
        Copy-Item (Split-Path $r.Snapshot) "$dir\snapshot" -Recurse
    }
    Get-ChildItem "$QueueOut\preserved" -Recurse -File | Get-FileHash |
        ConvertTo-Json -Depth 4 | Set-Content "$QueueOut\preserved_hashes.json"
    $snap=Save-BoardSnapshot "$Predecessor\shell_copy\tools\software" "$QueueOut\before_reset"
    if($snap.Code -ne 0 -or $snap.Data.ddr1.error_count -ne 0){throw 'Pre-reset hardware health failed'}
    foreach($profile in @('regression','atomic_threads','virtual_memory','ipc_signals',
                         'arithmetic','memory_patterns','rvv_context')){
        Invoke-ExtendedBatch $profile $profile
    }
    for($i=1;$i -le 20;$i++){Invoke-ExtendedBatch ('reboot_{0:d2}' -f $i) 'boot_smoke'}
    Invoke-ExtendedBatch 'soak4h' 'soak4h'
    if(@($script:results | Where-Object {!$_.Passed}).Count -eq 0){
        Invoke-ExtendedBatch 'soak24h' 'soak24h'
    } else {
        $script:results+=@{Name='soak24h';Passed=$false;Status='not_run_prerequisite_failure'}
    }
    if(@($script:results | Where-Object {!$_.Passed}).Count){
        Queue-State 'completed_with_failures_or_gaps'
    } else {
        Queue-State 'extended_userspace_passed' 'Does not accept untested DDR2/network/peripherals/full ISA'
    }
} catch {
    Queue-State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    Stop-Transcript
}
