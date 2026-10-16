#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Out,
      [Parameter(Mandatory=$true)][string]$ReportHashes)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$package='D:\fpga_runs\ara_mainrtl_20260930\package'
$audit='D:\fpga_runs\ara_stall_ila_audit_20261002_01'
$checkpoint='D:\fpga_runs\ara_stall_ila_closure_20261002_02\ara_dsa_vcu118_routed.dcp'
$expected='B3D9ECE26DA98419B3337F401B5A435E92D1494EFAEEC7B23AEB6CAAF79D9271'
$reports="$package\reports\audit_6a9a20ee1e23"
$resets='D:\fpga_runs\ara_stall_reset_review_20261002_01\evidence'
function RequireHash([string]$path,[string]$hash) {
    if ((Get-FileHash -LiteralPath $path).Hash -ne $hash) { throw "Hash mismatch: $path" }
}
if (Test-Path $Out) { throw 'Output already exists' }
if (@(Get-CimInstance Win32_Process -Filter "Name='vivado.exe'").Count) {
    throw 'Another Vivado process is active'
}
RequireHash $checkpoint $expected
RequireHash "$package\SHA256SUMS" '9DFEE610630BFC5F1087BA687A05E946623ABD4D569FF7417C6565F9E1CB61DD'
& py -3 "$package\scripts\verify_package.py"
if ($LASTEXITCODE -ne 0) { throw 'Frozen package verification failed' }
if ((Get-Content "$audit\completed_audit.txt" -Raw).Trim() -ne 'audit_6a9a20ee1e23') {
    throw 'Missing audit completion'
}
$inputRecord=Get-Content "$audit\inputs.json" -Raw | ConvertFrom-Json
if ($inputRecord.Checkpoint -ne $checkpoint -or $inputRecord.SHA256 -ne $expected) {
    throw 'Audit checkpoint mismatch'
}
RequireHash "$audit\audit_stall_ila.tcl" $inputRecord.ScriptSHA256
foreach ($name in @('original','observation')) {
    RequireHash "$resets\$name.txt" '380EB9738C487C08675B087EACF9E7A260313A3B1351BF08B746E8986B2E46E2'
}
$review=Get-Content $ReportHashes -Raw | ConvertFrom-Json
$actual=@(Get-ChildItem $reports -Filter '*.rpt' -File)
if ($actual.Count -ne @($review.PSObject.Properties).Count -or $actual.Count -lt 30) {
    throw 'Report inventory differs from reviewed evidence'
}
foreach ($file in $actual) { RequireHash $file.FullName $review.($file.Name) }
New-Item -ItemType Directory -Path $Out | Out-Null
Copy-Item $ReportHashes "$Out\reviewed_report_hashes.json"
Copy-Item (Join-Path $PSScriptRoot 'bitgen_stall_ila.tcl') $Out
$script="$Out\bitgen_stall_ila.tcl"
$scriptHash=(Get-FileHash $script).Hash
@{Checkpoint=$checkpoint; SHA256=$expected; Audit=$audit; Reports=$reports;
  ScriptSHA256=$scriptHash; DiagnosticOnly=$true; CDCSignoff=$false;
  LinuxPassed=$false; BoardModified=$false} |
    ConvertTo-Json | Set-Content "$Out\inputs.json" -Encoding UTF8
function State([string]$stage,[string]$message='') {
    @{Stage=$stage; Message=$message; Updated=(Get-Date -Format o); ProcessId=$PID;
      DiagnosticOnly=$true; CDCSignoff=$false; BoardModified=$false} |
        ConvertTo-Json | Set-Content "$Out\state.json" -Encoding UTF8
}
try {
    State 'bitgen'
    Set-Location $Out
    & D:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -notrace -nojournal `
        -log "$Out\vivado.log" -source $script -tclargs $package $checkpoint "$Out\bitstream"
    if ($LASTEXITCODE -ne 0) { throw 'Diagnostic bitgen failed' }
    RequireHash $checkpoint $expected
    RequireHash $script $scriptHash
    $artifacts=foreach ($ext in @('bit','ltx')) {
        $file=Get-Item "$Out\bitstream\ara_dsa_vcu118.$ext"
        if ($file.Length -eq 0) { throw 'Empty artifact' }
        @{Path=$file.FullName; Length=$file.Length; SHA256=(Get-FileHash $file.FullName).Hash}
    }
    $artifacts | ConvertTo-Json | Set-Content "$Out\artifacts.json" -Encoding UTF8
    State 'diagnostic_bitstream_ready_not_programmed'
} catch {
    State 'failed' ($_ | Out-String)
    exit 1
}
