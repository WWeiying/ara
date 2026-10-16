param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$checkpoint='D:\fpga_runs\ara_dual_floorplan_20261006_02\floorplanned_opt.dcp'
$package='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package'
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
if(Test-Path "$Root\started.json"){throw 'Output already used'}
@{Started=(Get-Date -Format o);Checkpoint=$checkpoint;SHA256=(Get-FileHash $checkpoint).Hash;
  Scope='Initialization-only Pblock ablation; not a timing or placement pass';BoardModified=$false} |
    ConvertTo-Json | Set-Content "$Root\started.json"
$argsList=@('-mode','batch','-notrace','-nojournal','-source',"$Root\probe_mig_without_pblocks.tcl",
    '-log',"$Root\vivado.log",'-tclargs',$checkpoint,$package,$Root)
$p=Start-Process -FilePath 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -ArgumentList $argsList -WorkingDirectory $Root -PassThru
$passed=$false
while(!$p.HasExited){
    Start-Sleep -Seconds 15
    if(Test-Path "$Root\vivado.log"){
        $log=Get-Content "$Root\vivado.log" -Raw
        if($log -match '(?m)^Phase 2 '){
            $workers=@(Get-CimInstance Win32_Process | Where-Object {
                $_.Name -eq 'vivado.exe' -and $_.CommandLine.Contains("$Root\probe_mig_without_pblocks.tcl")
            })
            if($workers.Count -ne 1){throw 'Cannot uniquely identify owned diagnostic process'}
            $passed=$true
            # Do not spend hours placing the intentionally un-floorplanned design.
            Stop-Process -Id $workers[0].ProcessId -ErrorAction Stop
            break
        }
    }
    $p.Refresh()
}
$p.WaitForExit()
@{Finished=(Get-Date -Format o);InitializationPassed=$passed;StoppedBeforeFullPlacement=$passed;
  ProcessExitCode=$p.ExitCode;TimingPassed=$false;BoardModified=$false} |
    ConvertTo-Json | Set-Content "$Root\result.json"
if(!$passed){exit 1}
