param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$audit='D:\fpga_runs\ara_dual_route_resume_20261006_01'
$checkpoint='D:\fpga_runs\ara_dual_floorplan_route_20261006_03\routed_before_physopt.dcp'
$package='D:\fpga_runs\ara_dual_reset_locality_20261005_01\package'
function State($name,$message='') {
    @{Stage=$name;Message=$message;Updated=(Get-Date -Format o);BoardModified=$false;
      HardwareValidated=$false;ManualCDCReviewComplete=$false;Profile='dual_ddr_ethernet'} |
        ConvertTo-Json | Set-Content "$Root\state.json" -Encoding UTF8
}
try {
    if(Test-Path "$Root\inputs.json"){throw 'Output already used'}
    if(@(Get-Process vivado -ErrorAction SilentlyContinue).Count){throw 'Vivado busy'}
    if((Get-Content "$audit\stage.txt" -Raw).Trim() -ne 'timing_closed_requires_drc_cdc_review_not_bitstream') {throw 'Audit incomplete'}
    $old=Get-Content "$audit\inputs.json" -Raw | ConvertFrom-Json
    foreach($p in $old.PSObject.Properties) {
        if((Get-FileHash $p.Name).Hash -ne $p.Value){throw "Audited input changed: $($p.Name)"}
    }
    $drc=Get-Content "$audit\drc.rpt" -Raw
    if($drc -notmatch 'REPORT SUMMARY' -or $drc -match '(?im)^\s*\|\s*[^|]+\|\s*(Error|Critical Warning)\s*\|') {throw 'Missing or blocking DRC'}
    $summary=Get-Content "$audit\timing_gate.rpt" -Raw
    $m=[regex]::Match($summary,'(?m)^\s*WNS\(ns\)[^\r\n]*\r?\n[^\r\n]*\r?\n([^\r\n]+)')
    if(!$m.Success){throw 'Timing summary missing'}
    $v=$m.Groups[1].Value.Trim() -split '\s+'
    if($v.Count -ne 12){throw 'Timing layout changed'}
    foreach($i in @(0,4,8)) {
        $slack=[double]::Parse($v[$i],[Globalization.CultureInfo]::InvariantCulture)
        if([double]::IsNaN($slack) -or [double]::IsInfinity($slack) -or $slack -lt 0 -or
            [double]$v[$i+1] -ne 0 -or [long]$v[$i+2] -ne 0 -or [long]$v[$i+3] -le 0){throw 'Timing failed'}
    }
    $inputs=@{}
    foreach($p in @($checkpoint,$PSCommandPath,"$Root\bitgen_dual_routed.tcl") +
        @(Get-ChildItem "$audit\*.rpt" | Select-Object -ExpandProperty FullName) +
        @(Get-ChildItem "$package\scripts\*.tcl" | Select-Object -ExpandProperty FullName)) {
        $inputs[$p]=(Get-FileHash $p).Hash
    }
    $inputs | ConvertTo-Json | Set-Content "$Root\inputs.json"
    State 'generating_test_bitstream' 'Manual CDC review and board validation remain open'
    Push-Location $Root
    try {
        & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal -source "$Root\bitgen_dual_routed.tcl" -log "$Root\vivado.log" -tclargs $package $checkpoint "$Root\bitstream" $audit
        $code=$LASTEXITCODE
    } finally {Pop-Location}
    foreach($p in $inputs.Keys){if((Get-FileHash $p).Hash -ne $inputs[$p]){throw "Input changed: $p"}}
    if($code -ne 0){throw "Bitgen failed: exit $code"}
    $artifacts=@{}
    foreach($ext in @('bit','ltx')) {
        $p="$Root\bitstream\ara_dsa_vcu118.$ext"
        if(!(Test-Path $p) -or (Get-Item $p).Length -eq 0){throw "Missing artifact: $p"}
        $artifacts[$p]=(Get-FileHash $p).Hash
    }
    $artifacts | ConvertTo-Json | Set-Content "$Root\artifacts.json"
    State 'bitstream_generated_not_board_validated' 'Manual CDC review remains open; no programming performed'
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
}
