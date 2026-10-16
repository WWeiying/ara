# Each workload gets the old single-DDR image; never programs a new build.
param([string]$Out,
      [int[]]$ImplementationPids=@(),
      [switch]$RestartConfirmed,
      [switch]$LibraryOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Assert-SingleDdrSnapshot($snapshot) {
    if($snapshot.identity.magic -ne 1095910466 -or $snapshot.identity.caps -ne 1){
        throw 'Unexpected board identity; stop without further resets'
    }
    if($null -eq $snapshot.core.retired -or $null -eq $snapshot.ddr1.error_count){
        throw 'Incomplete hardware snapshot'
    }
}
function Get-BatchResult($profile,$report,$testExit,$snapshot,$snapshotExit) {
    Assert-SingleDdrSnapshot $snapshot
    $expected=@{compute=13;storage=33;timers=13;process=13;shell_copy=1}[$profile]
    if($null -eq $expected){throw 'Unknown profile'}
    if($profile -eq 'shell_copy') {
        $completed=[int][bool]$report.passed
        $successful=$completed
        $stage='shell_copy'
    } else {
        if(@($report.planned).Count -ne $expected){throw 'Matrix inventory changed'}
        $completed=@($report.results).Count
        $successful=@($report.results | Where-Object {$_.passed -eq $true}).Count
        $stage=$report.state
    }
    return @{Profile=$profile;Passed=($report.passed -and $testExit -eq 0 -and
                $completed -eq $expected -and $successful -eq $expected -and
                $snapshotExit -eq 0 -and $snapshot.ddr1.error_count -eq 0);
             WorkloadPassed=[bool]$report.passed;ExitCode=$testExit;LastStage=$stage;
             Planned=$expected;Completed=$completed;Successful=$successful;
             SnapshotExit=$snapshotExit;DdrErrors=$snapshot.ddr1.error_count}
}
function Invoke-OldBoot($tools,$phase,$pids) {
    $script=Join-Path $tools 'test_mmu_board.ps1'
    $command="& '"+$script.Replace("'","''")+"' -Out '"+$phase.Replace("'","''")+"' -BootOnly"
    if(@($pids).Count){$command+=' -ImplementationPids @('+($pids -join ',')+')'}
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded | Out-Host
    return $LASTEXITCODE
}
function Save-BoardSnapshot($software,$destination) {
    & py -3 "$software\host_load.py" snapshot --probes 'D:\fpga_runs\ara_mmu_fix_20261003\release\bitstream_host_ethernet\ara_dsa_vcu118.ltx' --vivado 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' --out $destination | Out-Host
    $code=$LASTEXITCODE
    if(!(Test-Path "$destination\snapshot.json")){throw 'No snapshot: do not reset board'}
    $snapshot=Get-Content "$destination\snapshot.json" -Raw | ConvertFrom-Json
    Assert-SingleDdrSnapshot $snapshot
    return @{Code=$code;Data=$snapshot;Path="$destination\snapshot.json"}
}
function Invoke-Workload($tools,$phase,$profile) {
    if($profile -eq 'shell_copy') {
        & py -3 "$tools\check_linux_console.py" --port COM6 --out "$phase\matrix" --seconds 120 --tx-gap 0.02 --clear-line --serial-wheel "$phase\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl" | Out-Host
    } else {
        & py -3 "$tools\linux_stability.py" --profile $profile --repetitions 200 --out "$phase\matrix" --serial-wheel "$phase\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl" | Out-Host
    }
    return $LASTEXITCODE
}
function Run-IndependentBatches($root,$tools,$pids) {
    foreach($profile in @('compute','storage','timers','process','shell_copy')) {
        Verify-Tools
        $phase=Join-Path $root $profile
        State "$profile/reload_original"
        $bootExit=Invoke-OldBoot $tools $phase $pids
        if($bootExit -ne 0){throw "Boot/transport failed for $profile; preserve scene"}
        State "$profile/testing"
        $testExit=Invoke-Workload $tools $phase $profile
        if(!(Test-Path "$phase\matrix\report.json")){throw 'Missing workload evidence; preserve scene'}
        $report=Get-Content "$phase\matrix\report.json" -Raw | ConvertFrom-Json
        State "$profile/snapshot"
        $captured=Save-BoardSnapshot "$phase\tools\software" "$phase\after_matrix"
        $result=Get-BatchResult $profile $report $testExit $captured.Data $captured.Code
        $result.Report="$phase\matrix\report.json"
        $result.Snapshot=$captured.Path
        $script:results+=,$result
        State "$profile/recorded" 'Evidence saved before the next independent reload'
    }
    if(@($script:results | Where-Object {!$_.Passed}).Count){
        State 'completed_with_failures' 'All batches attempted; failed/unstarted cases remain failures/gaps'
    } else {
        State 'bounded_campaign_passed' 'Not full ISA, full RAM, C2 or long-duration acceptance'
    }
}
if($LibraryOnly){return}
if(!$RestartConfirmed){throw 'Explicit permission to archive and end the preserved board scene is required'}
if(!$Out -or (Test-Path $Out)){throw 'New evidence directory required'}
$reference=Get-Content "$PSScriptRoot\reference_report.json" -Raw | ConvertFrom-Json
if(!$reference.passed -or @($reference.results).Count -ne 72){throw 'Missing 72-group reference validation'}
New-Item -ItemType Directory $Out | Out-Null
$script:results=@()
$script:modified=$false
$script:inputs=@{}
$prior='D:\fpga_runs\ara_stability_campaign_20261004_01\compute\tools\software'
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Results=$script:results;Updated=(Get-Date -Format o);
      BoardModified=$script:modified;ProcessId=$PID;NewBuildProgrammed=$false;
      Image='original_single_ddr_mmu_repaired';ImplementationPids=$ImplementationPids} |
      ConvertTo-Json -Depth 10 | Set-Content "$Out\state.json" -Encoding UTF8
}
function Verify-Tools {
    foreach($p in $script:inputs.Keys){
        if((Get-FileHash $p).Hash -ne $script:inputs[$p]){throw "Campaign input changed: $p"}
    }
}
$lock=$null
Start-Transcript "$Out\flow.log"
try {
    $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
    foreach($f in Get-ChildItem $PSScriptRoot -File){$script:inputs[$f.FullName]=(Get-FileHash $f.FullName).Hash}
    $script:inputs | ConvertTo-Json | Set-Content "$Out\tool_hashes.json"
    State 'archiving_previous_evidence'
    $sources=@('D:\fpga_runs\ara_stability_rootcause_20261005_01',
               'D:\fpga_runs\ara_stability_campaign_20261004_01',
               'D:\fpga_runs\ara_old_image_reload_20261004_02\stability_01')
    $archive="$Out\preserved_scene"
    New-Item -ItemType Directory $archive | Out-Null
    $inventory=@()
    foreach($source in $sources) {
        foreach($file in Get-ChildItem $source -Recurse -File) {
            $relative=$file.FullName.Substring($source.Length).TrimStart('\')
            $target=Join-Path (Join-Path $archive (Split-Path $source -Leaf)) $relative
            New-Item -ItemType Directory (Split-Path $target) -Force | Out-Null
            $hash=(Get-FileHash $file.FullName).Hash
            Copy-Item -LiteralPath $file.FullName -Destination $target
            if((Get-FileHash $target).Hash -ne $hash){throw 'Archive copy hash mismatch'}
            $inventory+=@{Source=$file.FullName;Copy=$target;SHA256=$hash}
        }
    }
    $inventory | ConvertTo-Json -Depth 5 | Set-Content "$Out\preserved_scene_manifest.json"
    State 'final_nonfreezing_snapshot'
    $final=Save-BoardSnapshot $prior "$Out\before_reset"
    $final | ConvertTo-Json -Depth 10 | Set-Content "$Out\before_reset_result.json"
    Verify-Tools
    $script:modified=$true
    Run-IndependentBatches $Out $PSScriptRoot $ImplementationPids
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    Stop-Transcript
}
