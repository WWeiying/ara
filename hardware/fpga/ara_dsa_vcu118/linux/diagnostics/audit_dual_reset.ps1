param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Checkpoint)
$ErrorActionPreference='Stop'
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
if (Test-Path "$Root\started.json") {throw 'Output already used'}
@{Started=(Get-Date -Format o);Input=(Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256);
  BoardModified=$false;Scope='Read-only reset netlist audit'} |
  ConvertTo-Json -Depth 4 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -source "$Root\audit_dual_reset.tcl" -log "$Root\vivado.log" -tclargs $Checkpoint $Root
    $code=$LASTEXITCODE
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
