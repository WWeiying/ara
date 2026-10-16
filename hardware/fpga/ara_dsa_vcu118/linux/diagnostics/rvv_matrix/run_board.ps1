param([Parameter(Mandatory=$true)][string]$Root,[string]$Predecessor='', [string]$ReuseDirectory='')
$ErrorActionPreference='Stop'
$lock=$null
try {
    if($Predecessor){
        @{Stage='waiting_for_predecessor';Predecessor=$Predecessor;BoardReset=$false} |
            ConvertTo-Json | Set-Content -LiteralPath "$Root\state.json" -Encoding ascii
        $deadline=(Get-Date).AddHours(3)
        while($true){
            if((Get-Date) -gt $deadline){throw 'Predecessor wait expired'}
            $path=Join-Path $Predecessor 'state.json'
            if(Test-Path $path){
                $previous=Get-Content $path -Raw|ConvertFrom-Json
                if($previous.Stage -eq 'all_cases_finished_review_results'){break}
                if($previous.Stage -eq 'stopped_review_scene'){throw 'Predecessor scene must be reviewed'}
            }
            Start-Sleep -Seconds 60
        }
    }
    $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
    $state=@{Stage='testing_current_image';RTLModified=$false;BoardReset=$false;Updated=(Get-Date).ToString('o')}
    $state | ConvertTo-Json | Set-Content -LiteralPath "$Root\state.json" -Encoding ascii
    $argsList=@('-3','-X','utf8',"$Root\width_suite.py")
    if($ReuseDirectory){$argsList+=@('--reuse-directory',$ReuseDirectory)}
    & py @argsList *> "$Root\console.log"
    if($LASTEXITCODE -ne 0){throw 'Observer stopped; preserve report/UART scene before recovery'}
    $state.Stage='all_cases_finished_review_results'
    $state.Updated=(Get-Date).ToString('o')
    $state | ConvertTo-Json | Set-Content -LiteralPath "$Root\state.json" -Encoding ascii
} catch {
    @{Stage='stopped_review_scene';Error=$_.Exception.Message;RTLModified=$false;BoardReset=$false;Updated=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath "$Root\state.json" -Encoding ascii
    exit 1
} finally {
    if($lock){$lock.Dispose()}
}
