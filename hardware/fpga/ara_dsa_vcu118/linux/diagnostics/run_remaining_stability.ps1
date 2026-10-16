# Completes only the eight unstarted cases; prior failures remain immutable.
param([string]$RunOut,
      [string]$SourceRun='D:\fpga_runs\ara_independent_stability_20261005_01',
      [int[]]$OfflinePids=@(),
      [switch]$RestartConfirmed,
      [switch]$LibraryOnly)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$approved=$RestartConfirmed
$asLibrary=$LibraryOnly
. "$PSScriptRoot\run_independent_stability.ps1" -LibraryOnly
$script:remaining=@('pipes','metadata','links_permissions','fifo','parallel_wait','signal_term','cleanup','shell_copy')

function Get-RemainingResult($name,$report,$exitCode,$snapshot) {
    Assert-SingleDdrSnapshot $snapshot.Data
    if($name -notin $script:remaining){throw 'Unexpected selected case'}
    if($name -eq 'shell_copy'){
        $targetPassed=[bool]$report.passed
        $started=($null -ne $report.PSObject.Properties['command_sent'] -and $report.command_sent)
    } else {
        $expected=if($name -eq 'cleanup'){@('case_setup','cleanup')}else{@('case_setup',$name,'case_teardown')}
        if((@($report.planned.name) -join ',') -ne ($expected -join ',')){throw 'Selected-case inventory mismatch'}
        if($report.selected_case -ne $name){throw 'Wrong selected case'}
        $target=@($report.results | Where-Object {$_.name -eq $name})
        $started=$target.Count -eq 1
        $targetPassed=$started -and $target[0].passed
    }
    return @{Name=$name;Started=$started;CasePassed=$targetPassed;
             Passed=($targetPassed -and $report.passed -and $exitCode -eq 0 -and
                     $snapshot.Code -eq 0 -and $snapshot.Data.ddr1.error_count -eq 0);
             ExitCode=$exitCode;SnapshotExit=$snapshot.Code;DdrErrors=$snapshot.Data.ddr1.error_count}
}
function Invoke-RemainingWorkload($tools,$destination,$boot,$name) {
    $wheel="$boot\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl"
    if($name -eq 'shell_copy'){
        & py -3 "$tools\check_linux_console.py" --port COM6 --out $destination --seconds 120 --tx-gap 0.02 --clear-line --serial-wheel $wheel | Out-Host
    } else {
        & py -3 "$tools\linux_stability.py" --process-case $name --repetitions 200 --out $destination --serial-wheel $wheel | Out-Host
    }
    return $LASTEXITCODE
}
function Run-RemainingCases($root,$tools,$pids) {
    $ready=$false
    $bootNumber=0
    foreach($name in $script:remaining){
        Verify-RemainingTools
        if(!$ready){
            $bootNumber++
            $boot=Join-Path $root ('boot_{0:d2}' -f $bootNumber)
            Remaining-State "$name/reload_original"
            $script:modified=$true
            $code=Invoke-OldBoot $tools $boot $pids
            if($code -ne 0){
                $snap=Save-BoardSnapshot "$SourceRun\shell_copy\tools\software" "$boot\after_boot_failure"
                $script:results+=@{Name=$name;Started=$false;CasePassed=$false;Passed=$false;
                                  Status='not_run_boot_failure';BootExit=$code;Snapshot=$snap.Path}
                throw 'Original Linux did not boot; remaining cases not run; scene retained'
            }
            $ready=$true
        }
        $destination=Join-Path $root $name
        Remaining-State "$name/testing"
        $code=Invoke-RemainingWorkload $tools $destination $boot $name
        if(!(Test-Path "$destination\report.json")){throw 'Missing workload evidence; do not reset'}
        $report=Get-Content "$destination\report.json" -Raw | ConvertFrom-Json
        Remaining-State "$name/snapshot"
        $snap=Save-BoardSnapshot "$boot\tools\software" "$root\snapshots\$name"
        $result=Get-RemainingResult $name $report $code $snap
        $result.Report="$destination\report.json"
        $result.Snapshot=$snap.Path
        $result.Boot=$boot
        $script:results+=,$result
        Remaining-State "$name/recorded" 'Old failures are unchanged; only fresh selected-case results count'
        if($snap.Code -ne 0 -or $snap.Data.ddr1.error_count -ne 0){throw 'Hardware snapshot error; preserve board'}
        $ready=$result.Passed
    }
    if(@($script:results | Where-Object {!$_.Passed}).Count){
        Remaining-State 'remaining_completed_with_failures'
    }else{
        Remaining-State 'remaining_eight_passed' 'Does not clear the prior exec_loader/boot failures'
    }
}
if($asLibrary){return}
if(!$approved){throw 'Archive and reset approval required'}
if(!$RunOut -or (Test-Path $RunOut)){throw 'New evidence directory required'}
New-Item -ItemType Directory $RunOut | Out-Null
$script:results=@()
$script:modified=$false
function Remaining-State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$script:modified;NewBuildProgrammed=$false;SourceRun=$SourceRun;
      OriginalFailureRetained='exec_loader_timeout_and_later_init_timeout';
      Planned=$script:remaining;Results=$script:results} |
        ConvertTo-Json -Depth 10 | Set-Content "$RunOut\state.tmp" -Encoding UTF8
    Move-Item "$RunOut\state.tmp" "$RunOut\state.json" -Force
}
function Verify-RemainingTools {
    foreach($f in (Get-Content "$PSScriptRoot\frozen.json" -Raw | ConvertFrom-Json)){
        if((Get-FileHash (Join-Path $PSScriptRoot $f.Path)).Hash -ne $f.SHA256){throw 'Frozen input changed'}
    }
}
$lock=$null
Start-Transcript "$RunOut\flow.log"
try {
    Verify-RemainingTools
    $reference=Get-Content "$PSScriptRoot\reference_report.json" -Raw | ConvertFrom-Json
    if(!$reference.passed -or $reference.suite -ne 'isolated_remaining_process' -or
       @($reference.results).Count -ne 20){throw 'Missing isolated-case reference pass'}
    foreach($f in $reference.tool_hashes.PSObject.Properties){
        if((Get-FileHash (Join-Path $PSScriptRoot $f.Name)).Hash -ne $f.Value){throw 'Reference code changed'}
    }
    $prior=Get-Content "$SourceRun\state.json" -Raw | ConvertFrom-Json
    if($prior.Stage -ne 'stopped_for_review'){throw 'Predecessor changed; review before reset'}
    if((Get-ScheduledTask -TaskName 'AraIndependentStability20261005').State -in @('Running','Queued')){
        throw 'Predecessor still running'
    }
    $old=Get-Content "$SourceRun\process\matrix\report.json" -Raw | ConvertFrom-Json
    if($old.state -ne 'exec_loader' -or $old.passed -or @($old.results).Count -ne 5){throw 'Original case inventory changed'}
    $oldTail=@($old.planned | Select-Object -Skip 6 | ForEach-Object {$_.name})
    if(($oldTail -join ',') -ne ($script:remaining[0..6] -join ',')){throw 'Wrong pending-case list'}
    $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
    Remaining-State 'archiving_previous_scene'
    $selected=@('state.json','process\matrix','process\after_matrix','shell_copy\state.json',
                'shell_copy\flow.log','shell_copy\linux')
    $inventory=@()
    foreach($relative in $selected){
        $source=Join-Path $SourceRun $relative
        foreach($file in Get-ChildItem -LiteralPath $source -File -Recurse){
            $rel=$file.FullName.Substring($SourceRun.Length).TrimStart('\')
            $target=Join-Path "$RunOut\preserved_scene" $rel
            New-Item -ItemType Directory (Split-Path $target) -Force | Out-Null
            $hash=(Get-FileHash -LiteralPath $file.FullName).Hash
            Copy-Item -LiteralPath $file.FullName -Destination $target
            if((Get-FileHash -LiteralPath $target).Hash -ne $hash){throw 'Archive verification failed'}
            $inventory+=@{Source=$file.FullName;Copy=$target;SHA256=$hash}
        }
    }
    $inventory|ConvertTo-Json -Depth 5|Set-Content "$RunOut\archive_manifest.json"
    Remaining-State 'final_nonfreezing_snapshot'
    $snap=Save-BoardSnapshot "$SourceRun\shell_copy\tools\software" "$RunOut\before_reset"
    if($snap.Code -ne 0 -or $snap.Data.ddr1.error_count -ne 0){throw 'Pre-reset snapshot health failed; preserve scene'}
    Run-RemainingCases $RunOut $PSScriptRoot $OfflinePids
} catch {
    Remaining-State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    Stop-Transcript
}
