# Destructive FPGA SRAM reconfiguration, then original Linux + bounded shell test.
param([Parameter(Mandatory=$true)][string]$Out,
      [int[]]$ImplementationPids=@(),
      [switch]$BootOnly,
      [string]$TestSuiteDir='')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$release='D:\fpga_runs\ara_mmu_fix_20261003\release'
$prior='D:\fpga_runs\ara_stall_ila_board_20261002_02'
if(Test-Path $Out){throw 'Evidence directory already exists'}
# Only explicitly inspected offline implementation processes may coexist.
foreach($process in @(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'")) {
    if($process.ProcessId -notin $ImplementationPids -or
       $process.CommandLine -notmatch '-mode batch' -or
       $process.CommandLine -notmatch '(rebuild_mainrtl\.tcl.*-tclargs impl |rebuild_dual_cdc\.tcl |\-source ara_dsa_vcu118\.tcl )') {
        throw "Vivado busy/unreviewed process: $($process.ProcessId)"
    }
}
$artifacts=Get-Content "$release\bitstream_host_ethernet\bitstream.json" -Raw | ConvertFrom-Json
if($artifacts.CheckpointSHA256 -ne '5A6B6873916B78148B97B1D5ABFE4B9CD547294667D4FBD7A41C2587EFE793FE'){
    throw 'Unexpected source checkpoint'
}
if(@($artifacts.Outputs).Count -ne 2){throw 'Expected bit/probes pair'}
foreach($a in $artifacts.Outputs){
    if((Get-FileHash $a.Path).Hash -ne $a.Hash){throw 'Bit/probes hash mismatch'}
}
$images=@{
    'Image'='716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'
    'fw_jump.elf'='afa904f73c10cad298891fd02269dee5f544152d82b841929b92e9fbc3b07f92'
    'ara_vcu118.dtb'='a78f2160a4e1a7191df2f4ca4b012a9145b394ac6e9883031b2e0b94565157ef'
    'initramfs.cpio'='4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25'
    'firmware.elf'='26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2'
}
foreach($name in $images.Keys){
    if((Get-FileHash "$prior\$name").Hash -ne $images[$name]){throw "Original image mismatch: $name"}
}
$testImages=@{}
if($TestSuiteDir){
    $suite=Get-Content "$TestSuiteDir\build.json" -Raw | ConvertFrom-Json
    $reference=Get-Content "$TestSuiteDir\reference_report.json" -Raw | ConvertFrom-Json
    if($suite.state -ne 'built_needs_reference' -or !$suite.base_prefix_unchanged -or
       $suite.base_sha256 -ne $images['initramfs.cpio'] -or
       $suite.dtb_base_sha256 -ne $images['ara_vcu118.dtb'] -or !$reference.passed){
        throw 'Extended tools lack a reviewed original-image base/reference pass'
    }
    foreach($name in @('initramfs.cpio','ara_vcu118.dtb')){
        $expected=$suite.outputs.PSObject.Properties[$name].Value
        if((Get-FileHash "$TestSuiteDir\$name").Hash -ne $expected.sha256 -or
           (Get-Item "$TestSuiteDir\$name").Length -ne $expected.bytes){throw "Test image mismatch: $name"}
        $testImages[$name]=$expected.sha256
    }
    if($reference.initramfs_sha256 -ne $testImages['initramfs.cpio']){throw 'Reference uses another rootfs'}
}
New-Item -ItemType Directory $Out | Out-Null
Copy-Item "$prior\tools" "$Out\tools" -Recurse
Copy-Item "$PSScriptRoot\check_linux_console.py" "$Out\check_linux_console.py"
foreach($name in $images.Keys){Copy-Item "$prior\$name" $Out}
foreach($name in $testImages.Keys){Copy-Item "$TestSuiteDir\$name" "$Out\$name" -Force}
@{Artifacts=$artifacts; Images=$images; TestImageOverrides=$testImages; BootOnly=[bool]$BootOnly; ToolHashes=@(Get-ChildItem "$Out\tools" -Recurse -File | Get-FileHash)} |
    ConvertTo-Json -Depth 8 | Set-Content "$Out\inputs.json" -Encoding UTF8
$env:Path='D:\Xilinx\Vivado\2020.1\bin;D:\Xilinx\Vitis\2020.1\bin;'+$env:Path
$bit="$release\bitstream_host_ethernet\ara_dsa_vcu118.bit"
$ltx="$release\bitstream_host_ethernet\ara_dsa_vcu118.ltx"
$modified=$false
function State($stage,$message=''){
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);ProcessId=$PID;
      BoardModified=$modified} | ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
}
Start-Transcript "$Out\flow.log"
try {
    $modified=$true
    State 'programming'
    & vivado.bat -mode batch -notrace -nojournal -log "$Out\program.log" -source "$Out\tools\ethernet\program_host_image.tcl" -tclargs $bit $ltx --cold-no-reset
    if($LASTEXITCODE){throw 'FPGA programming failed'}
    State 'ethernet_initialization'
    & py -3 "$Out\tools\ethernet\ara_init.py" --elf "$Out\firmware.elf" --sha256 $images['firmware.elf'] --probes $ltx --out "$Out\ethernet_init" --fresh-bitstream-confirmed --prepare-phy-clock --vivado vivado.bat --xsct xsct.bat
    if($LASTEXITCODE){throw 'Ethernet initialization failed'}
    State 'original_kernel_boot' 'Optional /opt test-tools overlay recorded in inputs.json'
    & py -3 "$Out\tools\ethernet\ara_load.py" --elf "$Out\fw_jump.elf" --load "0x80200000:$Out\Image" --load "0x80100000:$Out\ara_vcu118.dtb" --load "0x88000000:$Out\initramfs.cpio" --probes $ltx --out "$Out\linux" --full-reset-confirmed --linux --port COM6 --seconds 180 --vivado vivado.bat
    if($LASTEXITCODE){throw 'Original Linux boot failed; preserve running board for diagnosis'}
    if($BootOnly){
        State 'original_linux_booted' 'Kernel/init marker only; independent workload must establish its own result'
        exit 0
    }
    State 'shell_memory_test'
    & py -3 "$Out\check_linux_console.py" --port COM6 --out "$Out\shell" --seconds 120 --tx-gap 0.02 --clear-line --serial-wheel "$Out\tools\software\vendor\pyserial-3.5-py2.py3-none-any.whl"
    if($LASTEXITCODE){throw 'Shell memory test failed; preserve board for diagnosis'}
    State 'original_linux_and_shell_smoke_passed' 'Bounded boot/shell/tmpfs test, not exhaustive Linux or RVV signoff'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
} finally {Stop-Transcript}
