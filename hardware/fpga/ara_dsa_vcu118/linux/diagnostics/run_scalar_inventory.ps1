#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$RunDir)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$package='D:\fpga_runs\ara_mainrtl_20260930\package'
$dcp='D:\fpga_runs\ara_mainrtl_20260930\runs\synth_3d28a8eb257a\ara_dsa_vcu118.dcp'
$hash='28998C0C59EE7FA6880508CAEF119C6EB7B5841E577BAF36EA2B98B324712FDB'
if(Test-Path -LiteralPath $RunDir){throw 'Existing output'}
New-Item -ItemType Directory -Path $RunDir | Out-Null
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      Checkpoint=$dcp;SHA256=$hash;BoardModified=$false} | ConvertTo-Json |
      Set-Content (Join-Path $RunDir 'state.json') -Encoding UTF8
}
try {
    State 'checking_frozen_input'
    if((Get-FileHash $dcp).Hash -ne $hash){throw 'Checkpoint hash mismatch'}
    Copy-Item (Join-Path $PSScriptRoot 'inventory_scalar_stall.tcl') $RunDir
    Set-Location $RunDir
    State 'reading_scalar_cache_mmu_inventory'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
      -log (Join-Path $RunDir 'vivado.log') -source (Join-Path $RunDir 'inventory_scalar_stall.tcl') `
      -tclargs $package $dcp (Join-Path $RunDir 'inventory') expanded
    if($LASTEXITCODE -ne 0){throw 'Inventory failed'}
    if(!(Test-Path (Join-Path $RunDir 'inventory\complete.txt'))){throw 'Missing completion marker'}
    if((Get-FileHash $dcp).Hash -ne $hash){throw 'Checkpoint changed'}
    State 'inventory_collected_not_diagnosed'
} catch { State 'failed' ($_|Out-String); exit 1 }
