param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$prior='D:\fpga_runs\ara_stall_ila_board_20261002_02'
$release='D:\fpga_runs\ara_dual_bitgen_20261006_01'
$images=@{
 'Image'='716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'
 'fw_jump.elf'='afa904f73c10cad298891fd02269dee5f544152d82b841929b92e9fbc3b07f92'
 'ara_vcu118.dtb'='a78f2160a4e1a7191df2f4ca4b012a9145b394ac6e9883031b2e0b94565157ef'
 'initramfs.cpio'='4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25'
 'firmware.elf'='26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2'
}
function State($name,$message='') {
 @{Stage=$name;Message=$message;Updated=(Get-Date -Format o);Profile='dual_ddr_ethernet';
   LinuxMemoryScope='Original single-bank device tree';FlashModified=$false} |
   ConvertTo-Json | Set-Content "$Out\linux_state.json"
}
try {
 if(Test-Path "$Out\ethernet_init"){throw 'Output already used'}
 if(@(Get-Process vivado,python,xsct -ErrorAction SilentlyContinue).Count){throw 'Board clients busy'}
 foreach($name in $images.Keys){
  if((Get-FileHash "$prior\$name").Hash -ne $images[$name]){throw "Image changed: $name"}
 }
 $artifacts=Get-Content "$release\artifacts.json" -Raw | ConvertFrom-Json
 foreach($p in $artifacts.PSObject.Properties){if((Get-FileHash $p.Name).Hash -ne $p.Value){throw 'Artifact changed'}}
 @{Images=$images;Artifacts=$artifacts;Tools=@(Get-ChildItem "$Out\tools" -Recurse -File | Get-FileHash)} |
  ConvertTo-Json -Depth 6 | Set-Content "$Out\linux_inputs.json"
 $env:Path='D:\Xilinx\Vivado\2020.1\bin;D:\Xilinx\Vitis\2020.1\bin;'+$env:Path
 $bit="$release\bitstream\ara_dsa_vcu118.bit"
 $ltx="$release\bitstream\ara_dsa_vcu118.ltx"
 State 'reprogramming_for_cold_contract'
 & vivado.bat -mode batch -notrace -nojournal -log "$Out\cold_program.log" -source "$Out\program_host_image.tcl" -tclargs $bit $ltx --cold-no-reset
 if($LASTEXITCODE){throw 'Cold programming failed'}
 State 'ethernet_initialization'
 & py -3 "$Out\tools\ethernet\ara_init.py" --elf "$prior\firmware.elf" --sha256 $images['firmware.elf'] --probes $ltx --out "$Out\ethernet_init" --fresh-bitstream-confirmed --prepare-phy-clock --vivado vivado.bat --xsct xsct.bat
 if($LASTEXITCODE){throw 'Ethernet initialization failed'}
 State 'ethernet_linux_load'
 & py -3 "$Out\tools\ethernet\ara_load.py" --elf "$prior\fw_jump.elf" --load "0x80200000:$prior\Image" --load "0x80100000:$prior\ara_vcu118.dtb" --load "0x88000000:$prior\initramfs.cpio" --probes $ltx --out "$Out\linux" --full-reset-confirmed --linux --port COM6 --seconds 180 --vivado vivado.bat
 if($LASTEXITCODE){throw 'Linux load/boot failed; preserve board for diagnosis'}
 State 'linux_init_marker_passed' 'Not exhaustive Linux or dual-bank Linux allocation validation'
} catch {
 State 'stopped_for_review' ($_ | Out-String)
 exit 1
}
