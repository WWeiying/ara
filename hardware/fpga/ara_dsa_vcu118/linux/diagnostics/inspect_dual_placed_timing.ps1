param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$BuildRoot)
$ErrorActionPreference='Stop'
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
$checkpoint=Join-Path $BuildRoot 'implementation\placed.dcp'
if (!(Test-Path -LiteralPath $checkpoint)) {throw 'Missing placed checkpoint'}
$state=Join-Path $BuildRoot 'state.json'
$previous=Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
$previous.Stage='stopped_by_user_for_timing_diagnosis'
$previous.Message='Implementation process tree stopped; placement retained; board untouched.'
$previous.Updated=Get-Date -Format o
$previous | ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -source "$Root\inspect_dual_placed_timing.tcl" -log "$Root\vivado.log" `
        -tclargs $checkpoint $Root inventory_only
    $code=$LASTEXITCODE
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;
      Scope='placed estimates only; no synthesis, placement, routing or bitgen'} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
