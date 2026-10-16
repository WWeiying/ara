# Fresh synthesis of sealed reset-corrected sources; never programs the board.
param([Parameter(Mandatory=$true)][string]$Bundle)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Bundle=(Resolve-Path $Bundle).Path
$package="$Bundle\package"
$tools="$Bundle\tools"
$out="$Bundle\runs"
$vivado='D:\Xilinx\Vivado\2020.1\bin\vivado.bat'
$lock=$null
$old=$env:ARA_FPGA_PROFILE
if(Test-Path $out){throw 'Output exists; do not restart completed work'}
if(@(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'").Count){throw 'Vivado already running; no process killed'}
New-Item -ItemType Directory $out | Out-Null
$inventory=(Get-FileHash "$package\SHA256SUMS").Hash
$token=$inventory.Substring(0,12).ToLower()
$hashes=@{}
foreach($file in @(Get-ChildItem $tools -File)){$hashes[$file.FullName]=(Get-FileHash $file.FullName).Hash}
$hashes | ConvertTo-Json | Set-Content "$Bundle\tool_hashes.json"
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      Profile='dual_ddr_ethernet';BoardModified=$false;AutomaticProgramming=$false;
      PackageSHA256=$inventory;SynthesisRun="synth_$token"} |
      ConvertTo-Json | Set-Content "$Bundle\state.json" -Encoding UTF8
}
function Verify {
    if((Get-FileHash "$package\SHA256SUMS").Hash -ne $inventory){throw 'Inventory changed'}
    foreach($path in $hashes.Keys){if((Get-FileHash $path).Hash -ne $hashes[$path]){throw "Tool changed: $path"}}
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Source verification failed'}
}
Start-Transcript -Path "$Bundle\flow.log" -NoClobber
try {
    State 'verify_frozen_sources'
    Verify
    $regression=Get-Content "$Bundle\tests\combined\report.json" -Raw | ConvertFrom-Json
    if(!$regression.passed){throw 'Actual combined wrapper regression missing/failed'}
    $reset=Get-Content "$Bundle\tests\reset\result.json" -Raw | ConvertFrom-Json
    if(!$reset.passed){throw 'Actual reset regression missing/failed'}
    $wrapperHash=(Get-FileHash "$package\rtl\board\dram_wrapper_xilinx.sv").Hash.ToLower()
    if($reset.wrapper_sha256 -ne $wrapperHash){throw 'Reset test used different wrapper'}
    $wrapperTests=@($regression.sources.PSObject.Properties | Where-Object {$_.Name.EndsWith('/rtl/board/dram_wrapper_xilinx.sv')})
    if($wrapperTests.Count -ne 1 -or $wrapperTests[0].Value -ne $wrapperHash){throw 'Combined test used different wrapper'}
    State 'prepare_ip' 'New isolated package; serial OOC preparation; board untouched'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$package\scripts\create_profile.ps1" -Profile dual_ddr_ethernet
    if($LASTEXITCODE -ne 0){throw 'IP preparation failed'}
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    $env:ARA_FPGA_PROFILE='dual_ddr_ethernet'
    Verify
    State 'fresh_top_synthesis' 'Includes new UI reset distribution stage on both DDR channels'
    & $vivado -mode batch -notrace -nojournal -source "$tools\rebuild_mainrtl.tcl" -log "$out\synthesis.log" -tclargs synth $package $out $token - -
    if($LASTEXITCODE -ne 0){throw 'Synthesis or strict setup/structural gate failed; reports preserved'}
    State 'verify_actual_reset_netlist'
    & $vivado -mode batch -notrace -nojournal -source "$tools\check_dual_reset_netlist.tcl" -log "$out\reset_netlist.log" -tclargs $package "synth_$token" $out
    if($LASTEXITCODE -ne 0){throw 'Full-netlist reset structural check failed'}
    Verify
    State 'synthesis_ready_for_physical_review' 'Review hold/skew and reset structure before applying measured SLR locality and starting implementation'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    $env:ARA_FPGA_PROFILE=$old
    Stop-Transcript
}
