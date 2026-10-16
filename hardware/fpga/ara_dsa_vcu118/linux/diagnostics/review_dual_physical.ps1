param([Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
if(Test-Path $Out){throw 'Review output already exists'}
$env:ARA_FPGA_PROFILE='dual_ddr_ethernet'
$lock=$null
try {
    $lock=[IO.File]::Open("$Bundle\package\build\managed\run.lock",'OpenOrCreate','ReadWrite','None')
    & py -3 "$Bundle\package\scripts\verify_package.py"
    if($LASTEXITCODE -ne 0){throw 'Package verification failed'}
    & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -nojournal -source "$PSScriptRoot\review_dual_physical.tcl" -log "$PSScriptRoot\physical_review.log" -tclargs "$Bundle\package" $Out
    if($LASTEXITCODE -ne 0 -or !(Test-Path "$Out\review_complete.txt")){throw 'Physical inventory incomplete'}
} finally {
    if($null -ne $lock){$lock.Dispose()}
}
