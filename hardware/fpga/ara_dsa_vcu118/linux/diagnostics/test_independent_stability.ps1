param([Parameter(Mandatory=$true)][string]$TestOut)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\run_independent_stability.ps1" -LibraryOnly
function Assert($condition,$message){if(!$condition){throw $message}}
$snap=[pscustomobject]@{identity=@{magic=1095910466;caps=1};core=@{retired=1};ddr1=@{error_count=0}}
$good=[pscustomobject]@{passed=$true;state='passed';planned=@(1..13);results=@(1..13 | ForEach-Object {@{passed=$true}})}
$r=Get-BatchResult compute $good 0 $snap 0
Assert $r.Passed 'complete workload'
$good.results[3].passed=$false
Assert (!(Get-BatchResult compute $good 0 $snap 0).Passed) 'oracle failure cannot count as success'
$good.results[3].passed=$true
Assert (!(Get-BatchResult compute $good 1 $snap 0).Passed) 'native error'
Assert (!(Get-BatchResult compute $good 0 $snap 1).Passed) 'snapshot cleanup error'
$snap.ddr1.error_count=1
Assert (!(Get-BatchResult compute $good 0 $snap 0).Passed) 'DDR error'
$snap.ddr1.error_count=0
$snap.identity.caps=3
$rejected=$false
try {Get-BatchResult compute $good 0 $snap 0 | Out-Null} catch {$rejected=$true}
Assert $rejected 'must not reset a different board profile'
$snap.identity.caps=1
Assert (Get-BatchResult shell_copy ([pscustomobject]@{passed=$true}) 0 $snap 0).Passed 'independent original smoke'

# Mock the irreversible operations while exercising the actual campaign order.
function Verify-Tools {}
function State($stage,$message=''){$script:stages+=,$stage}
function Invoke-OldBoot($tools,$phase,$pids){
    $script:events+=,('boot/'+(Split-Path $phase -Leaf))
    if($script:case -eq 'boot_failure'){return 1}
    return 0
}
function Invoke-Workload($tools,$phase,$profile){
    $script:events+=,('test/'+$profile)
    $n=@{compute=13;storage=33;timers=13;process=13;shell_copy=1}[$profile]
    New-Item -ItemType Directory "$phase\matrix" -Force | Out-Null
    $pass= !($script:case -eq 'workload_failure' -and $profile -eq 'compute')
    $report=@{passed=$pass;state='finished';planned=@(1..$n);results=@(1..$n | ForEach-Object {@{passed=$pass}})}
    $report | ConvertTo-Json -Depth 5 | Set-Content "$phase\matrix\report.json"
    if($pass){return 0}else{return 1}
}
function Save-BoardSnapshot($software,$destination){
    $script:events+=,('snapshot/'+(Split-Path (Split-Path $destination) -Leaf))
    if($script:case -eq 'snapshot_failure'){throw 'missing snapshot'}
    return @{Code=0;Data=$snap;Path='fixture'}
}
foreach($case in @('healthy','workload_failure','boot_failure','snapshot_failure')) {
    $script:case=$case
    $script:events=@();$script:stages=@();$script:results=@()
    $failed=$false
    try {Run-IndependentBatches (Join-Path $TestOut $case) $PSScriptRoot @(25376,6692)} catch {$failed=$true; Write-Output $_}
    if($case -in @('healthy','workload_failure')) {
        Assert (!$failed) "$case should attempt other groups"
        Assert ($script:results.Count -eq 5) 'all five independent batches'
        Assert ($script:events.Count -eq 15) 'each boot/test/snapshot performed once'
        Assert ($script:events[2] -eq 'snapshot/compute') 'snapshot before second boot'
        Assert ($script:events[3] -eq 'boot/storage') 'second boot follows preserved evidence'
        $expected=if($case -eq 'healthy'){'bounded_campaign_passed'}else{'completed_with_failures'}
        Assert ($script:stages[-1] -eq $expected) 'truthful final result'
    } else {
        Assert $failed 'infrastructure failure preserves scene'
        Assert ($script:results.Count -eq 0) 'no false completed batch'
        Assert (@($script:events | Where-Object {$_ -like 'boot/*'}).Count -eq 1) 'no reboot without evidence'
    }
    Write-Output "PASS $case"
}
Write-Output 'PASS verdict rejection cases'
