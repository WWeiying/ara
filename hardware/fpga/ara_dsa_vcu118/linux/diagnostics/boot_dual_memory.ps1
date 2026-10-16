param([Parameter(Mandatory=$true)][string]$Out, [switch]$Qwen3,
      [switch]$SkipMemoryTest, [switch]$SkipBoardHash, [switch]$QbsAkv)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$release='D:\fpga_runs\ara_dual_bitgen_20261006_01'
$prior='D:\fpga_runs\ara_stall_ila_board_20261002_02'
$lock=$null
function State($stage,$message='') {
 @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);FlashModified=$false;
   LinuxMemoryScope='DDR1 with original loader hole plus DDR2'} |
   ConvertTo-Json | Set-Content "$Out\state.json"
}
Start-Transcript "$Out\console.log" -NoClobber
try {
 $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
 if(@(Get-Process vivado,python,xsct -ErrorAction SilentlyContinue).Count){throw 'Board clients busy'}
 if(Test-Path "$Out\ethernet_init"){throw 'Output already used'}
 $manifest=Get-Content "$Out\payloads\manifest.json" -Raw | ConvertFrom-Json
 if(!$manifest.kernel_unchanged){throw 'Kernel changed unexpectedly'}
 foreach($p in $manifest.files.PSObject.Properties){
  if((Get-FileHash "$Out\payloads\$($p.Name)").Hash -ne $p.Value){throw 'Payload hash mismatch'}
 }
 foreach($p in $manifest.source.PSObject.Properties){
  if((Get-FileHash "$prior\$($p.Name)").Hash -ne $p.Value){throw 'Original payload mismatch'}
 }
 $artifacts=Get-Content "$release\artifacts.json" -Raw | ConvertFrom-Json
 foreach($p in $artifacts.PSObject.Properties){if((Get-FileHash $p.Name).Hash -ne $p.Value){throw 'Bitstream mismatch'}}
 $env:Path='D:\Xilinx\Vivado\2020.1\bin;D:\Xilinx\Vitis\2020.1\bin;'+$env:Path
 $bit="$release\bitstream\ara_dsa_vcu118.bit"
 $ltx="$release\bitstream\ara_dsa_vcu118.ltx"
 State 'cold_programming_same_dual_bitstream'
 & vivado.bat -mode batch -notrace -nojournal -log "$Out\cold_program.log" -source "$Out\program_host_image.tcl" -tclargs $bit $ltx --cold-no-reset
 if($LASTEXITCODE){throw 'Cold programming failed'}
 State 'ethernet_init'
 & py -3 "$Out\tools\ethernet\ara_init.py" --elf "$prior\firmware.elf" --sha256 26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2 --probes $ltx --out "$Out\ethernet_init" --fresh-bitstream-confirmed --prepare-phy-clock --vivado vivado.bat --xsct xsct.bat
 if($LASTEXITCODE){throw 'Ethernet init failed'}
 State 'booting_linux_with_both_banks'
 $payload="$Out\payloads"
 $bootSeconds=if($Qwen3){900}else{240}
 & py -3 "$Out\tools\ethernet\ara_load.py" --elf "$payload\fw_jump.elf" --load "0x80200000:$payload\Image" --load "0x80100000:$payload\ara_vcu118.dtb" --load "0x88000000:$payload\initramfs.cpio" --probes $ltx --out "$Out\linux" --full-reset-confirmed --linux --port COM6 --seconds $bootSeconds --vivado vivado.bat
 if($LASTEXITCODE){throw 'Linux boot failed; preserve board for diagnosis'}
 if(!$SkipMemoryTest){
 State 'verifying_physical_pages'
 & py -3 "$Out\verify_dual_linux.py" --out "$Out\memory_test" --software "$Out\tools\software" --probes $ltx --vivado vivado.bat
 if($LASTEXITCODE){throw 'Memory verification failed; preserve board for diagnosis'}
 State 'dual_linux_memory_verified' '64 MiB verified; not a full-capacity stress campaign'
 }
 if($Qwen3){
  State 'qwen3_inference'
  $hashArgs=@()
  if($SkipBoardHash){$hashArgs=@('--skip-board-hash')}
  if($QbsAkv){$hashArgs+=@('--qbs-akv')}
  & py -3 "$Out\run_qwen3.py" --out "$Out\qwen3" --software "$Out\tools\software" --manifest "$payload\manifest.json" @hashArgs
  if($LASTEXITCODE){throw 'Qwen3 inference did not pass; preserve UART evidence and board'}
  State 'qwen3_inference_completed' 'See qwen3/report.json and uart.bin for actual generation'
 }
} catch {
 State 'stopped_for_review' ($_ | Out-String)
 Write-Host ($_ | Out-String) -ForegroundColor Red
} finally {
 if($null -ne $lock){$lock.Dispose()}
 Stop-Transcript
}
