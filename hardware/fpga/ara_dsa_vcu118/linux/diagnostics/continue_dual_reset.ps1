# Independent continuation; reuses synthesis, never touches the running board.
param([Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Tools,
      [Parameter(Mandatory=$true)][string]$Out)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$package="$Bundle\package"
$anchor='D:\fpga_runs\ara_dual_locality_trial_20261005_02\locality_placed.dcp'
$baseline='D:\fpga_runs\ara_dual_inval_clock_fix_20261004\runs\synthesis_timing.rpt'
if(Test-Path $Out){throw 'Continuation output exists; nothing restarted'}
if(@(Get-CimInstance Win32_Process -Filter "Name = 'vivado.exe'").Count){throw 'Vivado busy'}
New-Item -ItemType Directory $Out | Out-Null
$inventory=(Get-FileHash "$package\SHA256SUMS").Hash
$token=$inventory.Substring(0,12).ToLower()
if($token -ne '249eae2d3065'){throw 'Unreviewed source package'}
$hashes=@{}
$inputs=@($anchor,$baseline,"$Bundle\runs\synthesis_timing.rpt","$package\SHA256SUMS")
$inputs+=@(Get-ChildItem $Tools -File | ForEach-Object FullName)
$inputs+=@(Get-ChildItem "$Bundle\runs\synth_$token" -Filter *.dcp | ForEach-Object FullName)
$inputs+=@(Get-ChildItem "$package\build" -Recurse -Filter *.dcp | ForEach-Object FullName)
foreach($path in $inputs){$hashes[$path]=(Get-FileHash $path).Hash}
$hashes | ConvertTo-Json | Set-Content "$Out\input_hashes.json"
$lock=$null
$old=$env:ARA_FPGA_PROFILE
function State($stage,$message='') {
    $state=@{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      Profile='dual_ddr_ethernet';BoardModified=$false;AutomaticProgramming=$false;Output=$Out}
    $state | ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
    $state | ConvertTo-Json | Set-Content "$Bundle\continuation_state.json" -Encoding UTF8
}
function Verify {
    foreach($path in $hashes.Keys){if((Get-FileHash $path).Hash -ne $hashes[$path]){throw "Changed input: $path"}}
    & py -3 "$package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package validation failed'}
}
Start-Transcript -Path "$Out\flow.log" -NoClobber
try {
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    $env:ARA_FPGA_PROFILE='dual_ddr_ethernet'
    State 'verify_existing_synthesis'
    Verify
    & py -3 "$Tools\check_reset_synthesis_delta.py" "$Bundle\runs\synthesis_timing.rpt" $baseline "$Out\synthesis_delta.json"
    if($LASTEXITCODE -ne 0){throw 'New synthesis violation requires review'}
    State 'implementation' 'Verify reset tree, optimize, measured SLR placement, bounded physopt and strict routed gates'
    & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -nojournal -source "$Tools\implement_dual_reset.tcl" -log "$Out\vivado.log" -tclargs $package $Tools $Out $token $anchor
    if($LASTEXITCODE -ne 0){throw 'Implementation stopped for review; checkpoints preserved'}
    Verify
    State 'routed_ready_for_full_audit' 'DRC/CDC release audit still required before bitstream; no board programming'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    Write-Output ($_ | Out-String)
    exit 1
} finally {
    if($null -ne $lock){$lock.Dispose()}
    $env:ARA_FPGA_PROFILE=$old
    Stop-Transcript
}
