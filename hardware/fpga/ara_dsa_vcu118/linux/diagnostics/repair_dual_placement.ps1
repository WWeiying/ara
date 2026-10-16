param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Checkpoint,
      [Parameter(Mandatory=$true)][string]$Tools)
$ErrorActionPreference='Stop'
if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy; no process killed'}
if(Test-Path "$Root\started.json"){throw 'Output already used'}
$inputs=@($Checkpoint,"$Tools\dual_cdc_preflight.tcl","$Root\repair_dual_placement.tcl",$PSCommandPath)
$hashes=@{}
foreach($path in $inputs){$hashes[$path]=(Get-FileHash $path).Hash}
@{Started=(Get-Date -Format o);Inputs=$hashes;BoardModified=$false;
  Scope='One placement-only physical optimization; no synthesis or board access'} |
  ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\repair_dual_placement.tcl" -log "$Root\vivado.log" -tclargs $Checkpoint $Tools $Root
    $code=$LASTEXITCODE
    foreach($path in $hashes.Keys){if((Get-FileHash $path).Hash -ne $hashes[$path]){throw "Input changed: $path"}}
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;
      Scope='Execution result only, not timing signoff'} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
