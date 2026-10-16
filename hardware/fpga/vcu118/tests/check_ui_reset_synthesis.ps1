param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
if (Test-Path "$Root\started.json") {throw 'Output already used'}
$inputs=@('rstgen.sv','rstgen_bypass.sv','dut.sv','check_ui_reset_synthesis.tcl') |
    ForEach-Object {Join-Path $Root $_}
$hashes=@($inputs | ForEach-Object {Get-FileHash -LiteralPath $_ -Algorithm SHA256})
@{Started=(Get-Date -Format o);Scope='Isolated reset structural synthesis only';
  Inputs=$hashes} |
  ConvertTo-Json -Depth 4 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
      -source "$Root\check_ui_reset_synthesis.tcl" -log "$Root\vivado.log" -tclargs $Root
    $code=$LASTEXITCODE
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
