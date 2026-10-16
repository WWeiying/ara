param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Xsa,
    [Parameter(Mandatory=$true)][string]$Linker,
    [string]$Vitis = 'D:\Xilinx\Vitis\2020.1'
)
$ErrorActionPreference = 'Stop'
$Sources = Join-Path $PSScriptRoot 'firmware'
$Platform = Join-Path $Workspace 'loader_platform'
$PlatformXsa = Join-Path $Platform 'hw\loader_no_bitstream.xsa'
$App = Join-Path $Workspace 'loader_app'
if (Test-Path -LiteralPath $App) { throw 'Refusing to overwrite an existing application' }
if ((Get-FileHash -LiteralPath $Xsa).Hash -ne (Get-FileHash -LiteralPath $PlatformXsa).Hash) {
    throw 'BSP platform does not match the selected XSA'
}
# Keep the reviewed BRAM/private-DDR layout independent of generated region names.
$Script = Get-Content -LiteralPath $Linker -Raw
if ($Script -notmatch 'ORIGIN\s*=\s*0xFF000000,\s*LENGTH\s*=\s*0x01000000' -or
    $Script -match 'ORIGIN\s*=\s*0x80000000') {
    throw 'Linker must reserve only the upper 16 MiB for loader DDR data'
}
$Src = Join-Path $App 'src'
New-Item -ItemType Directory -Path $Src | Out-Null
$Inputs = @($Xsa, $Linker, (Join-Path $PSScriptRoot 'loader_fast_probe_build.tcl'))
foreach ($Name in @('eth_loader_platform.c', 'eth_loader_platform.h',
                    'eth_fast_probe_frame.c', 'eth_fast_probe_frame.h',
                    'eth_fast_probe_main.c', 'eth_fast_load.c', 'eth_fast_load.h')) {
    $InputFile = Join-Path $Sources $Name
    Copy-Item -LiteralPath $InputFile -Destination $Src
    $Inputs += $InputFile
}
Copy-Item -LiteralPath $Linker -Destination (Join-Path $Src 'lscript.ld')
$env:PATH = (Join-Path $Vitis 'gnu\microblaze\nt\bin') + ';' + $env:PATH
& (Join-Path $Vitis 'bin\xsct.bat') (Join-Path $PSScriptRoot 'loader_fast_probe_build.tcl') $Workspace ara_cdma
if ($LASTEXITCODE -ne 0) { throw "Firmware compile/link failed: $LASTEXITCODE" }
$Build = Join-Path $App 'fast_probe_ara_cdma'
$Elf = Join-Path $Build 'fast_probe.elf'
& mb-readelf -l $Elf | Set-Content -LiteralPath (Join-Path $Build 'program_headers.txt')
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect firmware program headers' }
$Inputs += $Elf
$Inputs += Join-Path $Build 'fast_probe.map'
$Inputs += Join-Path $Platform 'mb\loader_domain\bsp\mb\include\xparameters.h'
$Inputs | ForEach-Object { Get-FileHash -LiteralPath $_ -Algorithm SHA256 } |
    Select-Object Path, Hash | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Build 'inputs.json')
'ARA_FIRMWARE_BUILT_MATCHING_XSA_NOT_BOARD_VALIDATED'
