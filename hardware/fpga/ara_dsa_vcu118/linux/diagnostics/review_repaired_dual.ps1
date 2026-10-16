param([Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
$env:ARA_FPGA_PROFILE='dual_ddr_ethernet'
$lock=$null
try {
    $lock=[IO.File]::Open("$Bundle\package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    & py -3 "$Bundle\package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
    $token=(Get-FileHash "$Bundle\package\SHA256SUMS").Hash.Substring(0,12).ToLower()
    & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -nojournal -source "$PSScriptRoot\review_repaired_dual.tcl" -log "$Out.log" -tclargs "$Bundle\package" $Out $token "$Bundle\runs\synthesis_timing.rpt"
    if($LASTEXITCODE -ne 0 -or !(Test-Path "$Out\completed.txt")){throw 'Review incomplete'}
} finally {
    if($null -ne $lock){$lock.Dispose()}
}
