param([string]$FixtureRoot)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\run_remaining_stability.ps1" -LibraryOnly
function Assert($condition,$message){if(!$condition){throw $message}}
function Verify-RemainingTools {}
function Remaining-State($stage,$message=''){$script:stages+=,$stage}
function Invoke-OldBoot($tools,$phase,$pids){
    $script:events+=,'boot'
    if($script:scenario -eq 'boot_failure'){return 1}
    return 0
}
function Save-BoardSnapshot($software,$destination){
    $script:events+=,'snapshot'
    if($script:scenario -eq 'snapshot_failure'){throw 'fixture missing snapshot'}
    return @{Code=0;Path='fixture';Data=[pscustomobject]@{identity=@{magic=1095910466;caps=1};core=@{retired=1};ddr1=@{error_count=0}}}
}
function Invoke-RemainingWorkload($tools,$destination,$boot,$name){
    $script:events+=,('test/'+$name)
    New-Item -ItemType Directory $destination -Force|Out-Null
    $passed= !($script:scenario -eq 'case_failure' -and $name -eq 'pipes')
    if($name -eq 'shell_copy'){$report=@{passed=$true;command_sent=$true}}else{
        $names=if($name -eq 'cleanup'){@('case_setup','cleanup')}else{@('case_setup',$name,'case_teardown')}
        $report=@{passed=$passed;selected_case=$name;planned=@($names|ForEach-Object {@{name=$_}});
                  results=@($names|ForEach-Object {@{name=$_;passed=$passed}})}
    }
    $report|ConvertTo-Json -Depth 5|Set-Content "$destination\report.json"
    if($passed){return 0}else{return 1}
}
foreach($scenario in @('healthy','case_failure','snapshot_failure','boot_failure')){
    $script:scenario=$scenario;$script:events=@();$script:stages=@();$script:results=@()
    $failed=$false
    try{Run-RemainingCases (Join-Path $FixtureRoot $scenario) $PSScriptRoot @()}catch{$failed=$true}
    $boots=@($script:events|Where-Object {$_ -eq 'boot'}).Count
    if($scenario -in @('healthy','case_failure')){
        Assert (!$failed) 'all independent cases should be attempted'
        Assert ($script:results.Count -eq 8) 'exactly eight selected cases'
        Assert (@($script:events|Where-Object {$_ -like 'test/*'}).Count -eq 8) 'no duplicate/existing tests'
        if($scenario -eq 'healthy'){
            Assert ($boots -eq 1) 'reuse a healthy Linux boot'
            Assert ($script:stages[-1] -eq 'remaining_eight_passed') 'truthful success'
        }else{
            Assert ($boots -eq 2) 'only reboot after saved failure'
            Assert ($script:events[2] -eq 'snapshot' -and $script:events[3] -eq 'boot') 'snapshot before recovery'
            Assert (!$script:results[0].Passed) 'failed case must remain failed'
            Assert ($script:stages[-1] -eq 'remaining_completed_with_failures') 'truthful failure'
        }
    }else{
        Assert $failed 'infrastructure failure stops resets'
        Assert ($boots -eq 1) 'no uncontrolled retry loop'
        if($scenario -eq 'boot_failure'){
            Assert (@($script:events|Where-Object {$_ -like 'test/*'}).Count -eq 0) 'boot failure is not a test attempt'
            Assert (!$script:results[0].Started) 'not-run recorded'
        }
    }
    Write-Output "PASS $scenario"
}
