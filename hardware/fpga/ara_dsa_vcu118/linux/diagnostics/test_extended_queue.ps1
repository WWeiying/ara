param([string]$FixtureRoot)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\queue_extended_stability.ps1" -LibraryOnly
function Assert($condition,$message){if(!$condition){throw $message}}
New-Item -ItemType Directory $FixtureRoot | Out-Null
$file=Join-Path $FixtureRoot 'evidence.json'
'{}' | Set-Content $file
$previous=[pscustomobject]@{Stage='bounded_campaign_passed';Results=@()}
Assert ((Get-QueueDisposition 'Running' $null) -eq 'waiting_for_existing_campaign') 'must wait without reading partial evidence'
foreach($p in @('compute','storage','timers','process','shell_copy')){
    $previous.Results+= [pscustomobject]@{Profile=$p;SnapshotExit=0;DdrErrors=0;Report=$file;Snapshot=$file}
}
Assert-Predecessor $previous
Assert ((Get-QueueDisposition 'Ready' $previous) -eq 'ready') 'completed predecessor'
$previous.Stage='completed_with_failures'
Assert-Predecessor $previous
$previous.Stage='stopped_for_review'
Assert ((Get-QueueDisposition 'Ready' $previous) -eq 'held_for_predecessor_review') 'failed predecessor must stay held'
$bad=$false;try{Assert-Predecessor $previous}catch{$bad=$true}
Assert $bad 'must not reset predecessor stopped scene'
$previous.Stage='bounded_campaign_passed'
$previous.Results[-1].SnapshotExit=1
$bad=$false;try{Assert-Predecessor $previous}catch{$bad=$true}
Assert $bad 'reject incomplete snapshot'
$previous.Results[-1].SnapshotExit=0
Remove-Item $file
$bad=$false;try{Assert-Predecessor $previous}catch{$bad=$true}
Assert $bad 'reject missing evidence'
$snap=@{Code=0;Data=[pscustomobject]@{identity=@{magic=1095910466;caps=1};core=@{retired=1};ddr1=@{error_count=0}}}
$report=[pscustomobject]@{passed=$true;planned=@(1,2);results=@(@{passed=$true},@{passed=$true})}
Assert (Get-ExtendedVerdict $report 0 $snap) 'complete pass'
$report.results[1].passed=$false
Assert (!(Get-ExtendedVerdict $report 0 $snap)) 'skip/failure not a pass'
$report.results[1].passed=$true
Assert (!(Get-ExtendedVerdict $report 1 $snap)) 'nonzero exit not a pass'
$snap.Data.ddr1.error_count=1
Assert (!(Get-ExtendedVerdict $report 0 $snap)) 'DDR errors not a pass'
Write-Output 'PASS queue predecessor and verdict guards (no board access)'
