param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Checkpoint,
      [Parameter(Mandatory=$true)][string]$Tools)
$ErrorActionPreference='Stop'
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
if (Test-Path "$Root\started.json") {throw 'Output already used'}
$hashes=@($Checkpoint,"$Tools\dual_cdc_preflight.tcl","$Root\optimize_dual_fanout.tcl" |
    ForEach-Object {Get-FileHash -LiteralPath $_ -Algorithm SHA256})
@{Started=(Get-Date -Format o);Inputs=$hashes;BoardModified=$false;
  Scope='One post-place fanout optimization; no synthesis, route or bitgen'} |
    ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -source "$Root\optimize_dual_fanout.tcl" -log "$Root\vivado.log" `
        -tclargs $Checkpoint $Tools $Root
    $code=$LASTEXITCODE
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;
      Scope='Optimization execution only; not timing signoff'} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
