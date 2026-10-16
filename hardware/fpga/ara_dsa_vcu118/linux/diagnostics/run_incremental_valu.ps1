$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$package='D:\fpga_runs\ara_valu_fix_20260928\package'
$out='D:\fpga_runs\ara_valu_incremental_20260929'
$reference='D:\fpga_runs\ara_postroute_close_20260928\ara_dsa_vcu118_routed.dcp'
$optimized='D:\fpga_runs\ara_valu_physical_20260929\impl_702699fe9998\ara_dsa_vcu118_opt.dcp'
$script=Join-Path $PSScriptRoot 'run_incremental_valu.tcl'
$expected=@{
    $reference='523e80416d02bc84ac4b6d8afd469c4d381da0b7b5147fdc0b2d47eea0bd1277'
    $optimized='a077c5861e50b739120b9553ba49194f33dc10197f757494099ceac0a542af56'
    "$package\SHA256SUMS"='f68f59d387c242b36125d78e4c01401121484fb72cb6f38f6a7117bb8206c1f0'
}
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      BoardModified=$false; Profile='host_ethernet'; AutomaticProgramming=$false} |
        ConvertTo-Json | Set-Content "$out\state.json" -Encoding UTF8
}
function Verify {
    foreach ($p in $expected.Keys) {
        if ((Get-FileHash -LiteralPath $p).Hash.ToLower() -ne $expected[$p]) {throw "Input changed: $p"}
    }
    & py -3 "$package\scripts\verify_package.py"
    if ($LASTEXITCODE -ne 0) {throw 'Frozen package verification failed'}
}
if (Test-Path $out) {throw 'Output exists; inspect instead of restarting'}
New-Item -ItemType Directory $out | Out-Null
$lock=$null
$profile=$env:ARA_FPGA_PROFILE
Start-Transcript -LiteralPath "$out\flow.log" -NoClobber
try {
    State 'verify_inputs'
    $lock=[IO.File]::Open("$package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado is busy'}
    $expected[$script]=(Get-FileHash $script).Hash.ToLower()
    $expected[$PSCommandPath]=(Get-FileHash $PSCommandPath).Hash.ToLower()
    Verify
    @{InputHashes=$expected; Reference=$reference; CurrentNetlist=$optimized;
      BaselineWNS=-0.819; BaselineTNS=-4863.854; BaselineFailingEndpoints=16501;
      Intent='Incremental physical reuse, unchanged RTL/constraints, no bitgen'} |
        ConvertTo-Json -Depth 4 | Set-Content "$out\inputs.json" -Encoding UTF8
    $env:ARA_FPGA_PROFILE='host_ethernet'
    State 'incremental_flow_running'
    Push-Location $out
    try {
        & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -source $script -log session.log -journal session.jou -tclargs $optimized $reference $package $out
        $code=$LASTEXITCODE
    } finally {Pop-Location}
    Verify
    if ($code -ne 0) {throw 'Incremental flow failed; checkpoint/reports preserved'}
    $stage=(Get-Content "$out\stage.txt" -Raw).Trim()
    if ($stage -ne 'timing_passed_requires_full_audit') {throw "Unexpected stage: $stage"}
    Get-FileHash "$out\routed.dcp" | ConvertTo-Json | Set-Content "$out\output_hash.json"
    State $stage
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
} finally {
    $env:ARA_FPGA_PROFILE=$profile
    if ($null -ne $lock) {$lock.Dispose()}
    Stop-Transcript
}
