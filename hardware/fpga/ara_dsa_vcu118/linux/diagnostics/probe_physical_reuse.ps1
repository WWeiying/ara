$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$out='D:\fpga_runs\ara_valu_reuse_probe_20260929'
$old='D:\fpga_runs\ara_postroute_close_20260928\ara_dsa_vcu118_routed.dcp'
$base='D:\fpga_runs\ara_valu_physical_20260929\impl_702699fe9998'
$current="$base\ara_dsa_vcu118_routed.dcp"
$optimized="$base\ara_dsa_vcu118_opt.dcp"
$script=Join-Path $PSScriptRoot 'probe_physical_reuse.tcl'
if (Test-Path $out) {throw 'Output exists; inspect instead of restarting'}
if (@(Get-Process vivado -ErrorAction SilentlyContinue).Count) {throw 'Vivado is busy'}
New-Item -ItemType Directory $out | Out-Null
$files=@($old,$current,$optimized,$script)
$before=@($files | ForEach-Object {Get-FileHash -LiteralPath $_})
$before | ConvertTo-Json | Set-Content "$out\inputs.json"
try {
    Push-Location $out
    try {
        & 'D:\Xilinx\Vivado\2020.1\bin\vivado.bat' -mode batch -notrace -source $script -log session.log -journal session.jou -tclargs $old $current $optimized $out
        if ($LASTEXITCODE -ne 0) {throw 'Probe failed; inspect session.log'}
    } finally {Pop-Location}
    foreach ($entry in $before) {
        if ((Get-FileHash -LiteralPath $entry.Path).Hash -ne $entry.Hash) {throw 'Input changed'}
    }
    'Read-only collection complete; no synthesis, implementation or programming.' | Set-Content "$out\complete.txt"
} catch {
    ($_ | Out-String) | Set-Content "$out\error.txt"
    exit 1
}
