param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Checkpoint)
$ErrorActionPreference='Stop'
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
if (Test-Path "$Root\started.json") {throw 'Output already used'}
$hashes=@($Checkpoint,"$Root\trial_fifo_select_placement.tcl" |
    ForEach-Object {Get-FileHash -LiteralPath $_ -Algorithm SHA256})
@{Started=(Get-Date -Format o);Inputs=$hashes;BoardModified=$false;
  Scope='Local FIFO read selector optimization only; checkpoint does not contain new reset RTL'} |
  ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
      -source "$Root\trial_fifo_select_placement.tcl" -log "$Root\vivado.log" -tclargs $Checkpoint $Root
    $code=$LASTEXITCODE
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;
      Scope='Selector experiment only, not reset fix or timing signoff'} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
