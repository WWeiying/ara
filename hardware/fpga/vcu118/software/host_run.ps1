# Pass Python arguments unchanged; use a Vivado-enabled shell or --vivado PATH.
# Example: .\host_run.ps1 load --elf .\host_smoke.elf --full-reset-confirmed --out D:\runs\host01
$ErrorActionPreference = 'Stop'
& py -3 (Join-Path $PSScriptRoot 'host_load.py') @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
