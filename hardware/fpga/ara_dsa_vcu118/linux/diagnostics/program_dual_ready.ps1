param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$release='D:\fpga_runs\ara_dual_bitgen_20261006_01'
$package='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package'
$modified=$false
function State($stage,$message='') {
    @{Stage=$stage;Message=$message;Updated=(Get-Date -Format o);BoardModified=$modified;
      LinuxBooted=$false;FlashModified=$false} | ConvertTo-Json | Set-Content "$Out\state.json"
}
try {
    if(Test-Path "$Out\inputs.json"){throw 'Output already used'}
    if(@(Get-Process vivado,python,xsct -ErrorAction SilentlyContinue).Count){throw 'Potential board client running'}
    $manifest=Get-Content "$release\artifacts.json" -Raw | ConvertFrom-Json
    if(@($manifest.PSObject.Properties).Count -ne 2){throw 'Expected bit and probes'}
    foreach($p in $manifest.PSObject.Properties){
        if((Get-FileHash $p.Name).Hash -ne $p.Value){throw 'Artifact hash mismatch'}
    }
    $bit="$release\bitstream\ara_dsa_vcu118.bit"
    $ltx="$release\bitstream\ara_dsa_vcu118.ltx"
    $rollback='D:\fpga_runs\ara_mmu_fix_20261003\release\bitstream_host_ethernet'
    $restore=@(Get-FileHash "$rollback\ara_dsa_vcu118.bit","$rollback\ara_dsa_vcu118.ltx")
    @{Artifacts=$manifest;Rollback=$restore;ProgramScript=(Get-FileHash "$Out\program_host_image.tcl")} |
        ConvertTo-Json -Depth 6 | Set-Content "$Out\inputs.json"
    $modified=$true
    State 'programming_sram'
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -log "$Out\program.log" -source "$Out\program_host_image.tcl" -tclargs $bit $ltx --cold-no-reset
    if($LASTEXITCODE){throw 'Programming/board-ready failed; inspect program.log'}
    State 'collecting_snapshot'
    & py -3 "$package\software\host_load.py" snapshot --probes $ltx --out "$Out\snapshot" --vivado D:\Xilinx\Vivado\2020.1\bin\vivado.bat
    if($LASTEXITCODE){throw 'Snapshot failed'}
    State 'programmed_ready_snapshot_collected' 'Not DDR traffic validation or Linux boot'
} catch {
    State 'stopped_for_review' ($_ | Out-String)
    exit 1
}
