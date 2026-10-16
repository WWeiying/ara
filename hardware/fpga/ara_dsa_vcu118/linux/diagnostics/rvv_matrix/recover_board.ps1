param([Parameter(Mandatory=$true)][string]$Root,[switch]$RestartAuthorized)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Set-StrictMode -Version Latest
if(!$RestartAuthorized){throw 'Unchanged-image restart authorization required'}
$lock=$null
$boardReset=$false
$old='D:\fpga_runs\ara_dual_linux_memory_20261006_01'
$release='D:\fpga_runs\ara_dual_bitgen_20261006_01'
$payload='D:\fpga_runs\ara_hw_campaign_20261008_02\payloads'
function State($stage,$message=''){
    @{Stage=$stage;Message=$message;Updated=(Get-Date).ToString('o');RTLModified=$false;
      BoardReset=$script:boardReset;OriginalImageRestart=$script:boardReset;ProcessId=$PID} |
        ConvertTo-Json|Set-Content "$Root\state.json" -Encoding ascii
}
try{
    $lock=[IO.File]::Open('D:\fpga_runs\ara_board_test.lock','OpenOrCreate','ReadWrite','None')
    $inputs=Get-Content "$Root\recovery.json" -Raw|ConvertFrom-Json
    if((Get-FileHash "$Root\previous_report.json").Hash.ToLower() -ne $inputs.previous_report_sha256){throw 'Scene changed'}
    $scene=Get-Content "$Root\previous_report.json" -Raw|ConvertFrom-Json
    if(!$scene.progress_diagnosis.stalled -or $scene.results[-1].status -ne 'stalled'){throw 'No confirmed stall'}
    $original=Get-Content 'D:\fpga_runs\ara_hw_campaign_20261008_03\payloads\manifest.json' -Raw|ConvertFrom-Json
    foreach($p in $original.files.PSObject.Properties){
        if((Get-FileHash "$payload\$($p.Name)").Hash -ne $p.Value){throw 'Original payload changed'}
    }
    if((Get-FileHash "$payload\initramfs.cpio").Hash.ToLower() -ne $inputs.base_initramfs_sha256){throw 'Base rootfs differs'}
    if((Get-FileHash "$Root\initramfs.cpio").Hash.ToLower() -ne $inputs.initramfs_sha256){throw 'Test overlay changed'}
    if((Get-FileHash "$payload\ara_vcu118.dtb").Hash.ToLower() -ne $inputs.base_dtb_sha256){throw 'Base DTB differs'}
    if((Get-FileHash "$Root\ara_vcu118.dtb").Hash.ToLower() -ne $inputs.dtb_sha256){throw 'Overlay DTB changed'}
    if((Get-FileHash "$payload\fw_jump.elf").Hash.ToLower() -ne $inputs.base_firmware_sha256){throw 'Base firmware differs'}
    if((Get-FileHash "$Root\fw_jump.elf").Hash.ToLower() -ne $inputs.firmware_sha256){throw 'Embedded DTB changed'}
    $artifacts=Get-Content "$release\artifacts.json" -Raw|ConvertFrom-Json
    foreach($p in $artifacts.PSObject.Properties){if((Get-FileHash $p.Name).Hash -ne $p.Value){throw 'Bitstream changed'}}
    $env:Path='D:\Xilinx\Vivado\2020.1\bin;D:\Xilinx\Vitis\2020.1\bin;'+$env:Path
    $ltx="$release\bitstream\ara_dsa_vcu118.ltx"
    $boardReset=$true
    State 'programming_original_image'
    & vivado.bat -mode batch -notrace -nojournal -log "$Root\program.log" -source "$old\program_host_image.tcl" -tclargs "$release\bitstream\ara_dsa_vcu118.bit" $ltx --cold-no-reset
    if($LASTEXITCODE){throw 'Original-image programming failed'}
    State 'initializing_ethernet'
    & py -3 "$old\tools\ethernet\ara_init.py" --elf D:\fpga_runs\ara_stall_ila_board_20261002_02\firmware.elf --sha256 26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2 --probes $ltx --out "$Root\ethernet_init" --fresh-bitstream-confirmed --prepare-phy-clock --vivado vivado.bat --xsct xsct.bat
    if($LASTEXITCODE){throw 'Ethernet initialization failed'}
    State 'booting_original_kernel_with_test_overlay'
    & py -3 "$old\tools\ethernet\ara_load.py" --elf "$Root\fw_jump.elf" --load "0x80200000:$payload\Image" --load "0x80100000:$Root\ara_vcu118.dtb" --load "0x88000000:$Root\initramfs.cpio" --probes $ltx --out "$Root\linux" --full-reset-confirmed --linux --port COM6 --seconds 240 --vivado vivado.bat
    if($LASTEXITCODE){throw 'Linux boot failed; scene preserved'}
    State 'exposing_preloaded_tests'
    & py -3 "$Root\preload_guest.py" --out "$Root\preload" --guest-directory $inputs.guest_directory --source-directory $inputs.preload_directory *> "$Root\preload_console.log"
    if($LASTEXITCODE){throw 'Test preload unavailable; no case executed'}
    State 'remaining_tests_running'
    @{Stage='testing_current_image';RecoveryRoot=$Root;Updated=(Get-Date).ToString('o')} |
        ConvertTo-Json|Set-Content "$Root\resume\state.json" -Encoding ascii
    & py -3 -X utf8 "$Root\resume\width_suite.py" --reuse-directory $inputs.guest_directory *> "$Root\resume\console.log"
    if($LASTEXITCODE){throw 'Remaining observer stopped; preserve new scene'}
    @{Stage='all_cases_finished_review_results';RecoveryRoot=$Root;Updated=(Get-Date).ToString('o')} |
        ConvertTo-Json|Set-Content "$Root\resume\state.json" -Encoding ascii
    State 'remaining_cases_finished_review_results'
}catch{
    State 'stopped_review_scene' ($_|Out-String)
    @{Stage='stopped_review_scene';Error=($_|Out-String);RecoveryRoot=$Root} |
        ConvertTo-Json|Set-Content "$Root\resume\state.json" -Encoding ascii
    exit 1
}finally{if($lock){$lock.Dispose()}}
