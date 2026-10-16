#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$build='D:\fpga_runs\ara_stall_ila_bitgen_20261002_01'
$prior='D:\fpga_runs\ara_mainrtl_board_recovered_20261002'
if (Test-Path $Out) { throw 'Existing evidence directory' }
if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) { throw 'Vivado busy' }
$state=Get-Content "$build\state.json" -Raw | ConvertFrom-Json
if ($state.Stage -ne 'diagnostic_bitstream_ready_not_programmed') { throw 'Bitgen not complete' }
$artifacts=Get-Content "$build\artifacts.json" -Raw | ConvertFrom-Json
if (@($artifacts).Count -ne 2) { throw 'Expected matching BIT and LTX pair' }
foreach ($artifact in $artifacts) {
    if ((Get-FileHash $artifact.Path).Hash -ne $artifact.SHA256) { throw 'Artifact changed' }
}
$imageHashes=@{
    'Image'='716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'
    'fw_jump.elf'='afa904f73c10cad298891fd02269dee5f544152d82b841929b92e9fbc3b07f92'
    'ara_vcu118.dtb'='a78f2160a4e1a7191df2f4ca4b012a9145b394ac6e9883031b2e0b94565157ef'
    'initramfs.cpio'='4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25'
    'firmware.elf'='26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2'
}
foreach ($name in $imageHashes.Keys) {
    if ((Get-FileHash "$prior\$name").Hash -ne $imageHashes[$name]) { throw "Image changed: $name" }
}
New-Item -ItemType Directory -Path $Out | Out-Null
Copy-Item "$prior\tools" "$Out\tools" -Recurse
Copy-Item (Join-Path $PSScriptRoot 'capture_stall_ila.tcl') "$Out\tools\ethernet"
foreach ($name in $imageHashes.Keys) { Copy-Item "$prior\$name" $Out }
$toolHashes=@(Get-ChildItem "$Out\tools" -Recurse -File | Get-FileHash)
@{Build=$build; Artifacts=$artifacts; ImageHashes=$imageHashes; Tools=$toolHashes;
  OriginalRun=$prior; DiagnosticOnly=$true; LinuxPassed=$false} |
    ConvertTo-Json -Depth 8 | Set-Content "$Out\inputs.json" -Encoding UTF8
$env:Path='D:\Xilinx\Vivado\2020.1\bin;D:\Xilinx\Vitis\2020.1\bin;'+$env:Path
$bit="$build\bitstream\ara_dsa_vcu118.bit"
$ltx="$build\bitstream\ara_dsa_vcu118.ltx"
$boardModified=$false
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      BoardModified=$boardModified; DiagnosticOnly=$true; LinuxPassed=$false} |
        ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
}
Start-Transcript "$Out\flow.log"
try {
    $boardModified=$true
    State 'programming'
    & vivado.bat -mode batch -notrace -nojournal -log "$Out\program.log" -source "$Out\tools\ethernet\program_host_image.tcl" -tclargs $bit $ltx --cold-no-reset
    if ($LASTEXITCODE) { throw 'Programming failed' }
    State 'ethernet_initialization'
    & py -3 "$Out\tools\ethernet\ara_init.py" --elf "$Out\firmware.elf" --sha256 $imageHashes['firmware.elf'] --probes $ltx --out "$Out\ethernet_init" --fresh-bitstream-confirmed --prepare-phy-clock --vivado vivado.bat --xsct xsct.bat
    if ($LASTEXITCODE) { throw 'Ethernet initialization failed' }
    State 'linux_load_and_boot'
    & py -3 "$Out\tools\ethernet\ara_load.py" --elf "$Out\fw_jump.elf" --load "0x80200000:$Out\Image" --load "0x80100000:$Out\ara_vcu118.dtb" --load "0x88000000:$Out\initramfs.cpio" --probes $ltx --out "$Out\linux" --full-reset-confirmed --linux --port COM6 --seconds 180 --vivado vivado.bat
    $loadCode=$LASTEXITCODE
    $report=Get-Content "$Out\linux\report.json" -Raw | ConvertFrom-Json
    if (-not $report.execution_started) { throw 'No execution established; preserve board' }
    State 'capturing' "Loader exit=$loadCode; capture is not a diagnosis"
    & vivado.bat -mode batch -notrace -nojournal -log "$Out\capture.log" -source "$Out\tools\ethernet\capture_stall_ila.tcl" -tclargs $ltx "$Out\capture"
    if ($LASTEXITCODE) { throw 'Capture failed; preserve board' }
    State 'captured_needs_analysis' "Loader exit=$loadCode; do not reset board"
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally { Stop-Transcript }
