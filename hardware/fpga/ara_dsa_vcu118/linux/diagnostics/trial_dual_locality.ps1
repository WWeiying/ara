param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$BuildRoot)
$ErrorActionPreference='Stop'
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado busy'}
if (Test-Path "$Root\started.json") {throw 'Trial already started; use a new directory'}
$placed=Join-Path $BuildRoot 'implementation\placed.dcp'
$optimized=Join-Path $BuildRoot 'implementation\impl_cdc_d482b5a035f2\ara_dsa_vcu118_opt.dcp'
$tools=Join-Path $BuildRoot 'tools'
$inputs=@($placed,$optimized,"$tools\dual_cdc_preflight.tcl",
          "$Root\dual_slr_locality.tcl","$Root\trial_dual_locality.tcl")
$hashes=@($inputs | ForEach-Object { Get-FileHash -LiteralPath $_ -Algorithm SHA256 })
@{Started=(Get-Date -Format o);BoardModified=$false;Inputs=$hashes;
  Scope='Placement locality experiment only; no synthesis, routing, bitgen or programming'} |
  ConvertTo-Json -Depth 5 | Set-Content "$Root\started.json" -Encoding UTF8
Push-Location $Root
try {
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -source "$Root\trial_dual_locality.tcl" -log "$Root\vivado.log" `
        -tclargs $placed $optimized $tools $Root
    $code=$LASTEXITCODE
    @{ExitCode=$code;Finished=(Get-Date -Format o);BoardModified=$false;
      Scope='Placement experiment only; not timing signoff'} |
      ConvertTo-Json | Set-Content "$Root\result.json" -Encoding UTF8
    exit $code
} finally {Pop-Location}
