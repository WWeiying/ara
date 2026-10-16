param([Parameter(Mandatory=$true)][string]$QueueOut,
      [string]$TaskName='AraExtendedStability20261005',
      [int[]]$AllowedVivadoPids=@(),
      [switch]$RestartConfirmed)
$ErrorActionPreference='Stop'
if(!$RestartConfirmed){throw 'Archive/reset approval required'}
if(Test-Path $QueueOut){throw 'Queue directory already exists'}
if(Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue){throw 'Task already exists'}
foreach($f in (Get-Content "$PSScriptRoot\frozen.json" -Raw | ConvertFrom-Json)){
    if((Get-FileHash (Join-Path $PSScriptRoot $f.Path)).Hash -ne $f.SHA256){throw 'Frozen input mismatch'}
}
$command="& '$PSScriptRoot\queue_extended_stability.ps1' -QueueOut '$QueueOut' -RestartConfirmed"
if(@($AllowedVivadoPids).Count){$command+=' -AllowedVivadoPids @('+($AllowedVivadoPids -join ',')+')'}
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
$principal=New-ScheduledTaskPrincipal -UserId 'oneol' -LogonType Interactive -RunLevel Highest
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 4) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "QUEUED $TaskName $QueueOut"
