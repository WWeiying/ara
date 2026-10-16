param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Sources,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Vitis = 'D:\Xilinx\Vitis\2020.1'
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'Select a new independent firmware workspace' }
foreach ($name in @('loader_platform', 'loader_app\src')) {
    if (!(Test-Path -LiteralPath (Join-Path $Workspace $name))) { throw "Missing $name" }
}
New-Item -ItemType Directory -Path $Output | Out-Null
Copy-Item -LiteralPath (Join-Path $Workspace 'loader_platform') -Destination $Output -Recurse
$app = Join-Path $Output 'loader_app'
New-Item -ItemType Directory -Path $app | Out-Null
Copy-Item -LiteralPath (Join-Path $Workspace 'loader_app\src') -Destination $app -Recurse
foreach ($name in @('eth_fast_load.c', 'eth_fast_load.h', 'eth_fast_probe_main.c')) {
    Copy-Item -LiteralPath (Join-Path $Sources $name) -Destination (Join-Path $app 'src')
}
$env:PATH = (Join-Path $Vitis 'gnu\microblaze\nt\bin') + ';' + $env:PATH
& (Join-Path $Vitis 'bin\xsct.bat') (Join-Path $Sources 'loader_fast_probe_build.tcl') $Output ara_cdma
if ($LASTEXITCODE -ne 0) { throw "Firmware compile/link failed: $LASTEXITCODE" }
'ARA_FIRMWARE_COMPILE_CHECK_PASSED_NOT_FINAL_XSA_OR_BOARD_VALIDATION'
