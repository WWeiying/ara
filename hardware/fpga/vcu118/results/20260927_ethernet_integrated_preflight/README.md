# Shared-DDR integration preflight

No combined full synthesis/implementation or board programming was performed
for this evidence set. The standalone board throughput is not an integrated
throughput result.

- `shared_run.log` / `shared_result.json`: VCS, 72 checks; source hashes included.
- `wrapper_run.log` / `wrapper_result.json`: actual generated loader port
  contract and Ara wrapper reset tests; vendor PHY implementation is stubbed.
- `xsa_check.json`: 28 checks of actual generated hardware metadata, including
  cache/offload configuration, CDMA DRE/width, clock and reset connectivity.
- `program_headers.txt`, `fast_probe.map`, `inputs.json`: final-XSA BSP firmware
  link, artifact paths and SHA256 hashes. Windows workspace:
  `D:/fpga_runs/ara_loader_shared_bsp_04`.

Firmware load segments:

| Region | Address | Memory bytes | Purpose |
| --- | --- | --- | --- |
| BRAM | `0x00000000` | `0x28` | vectors |
| BRAM | `0x00000050` | `0x24568` | code, data, stack, heap |
| Private DDR | `0xFF000000` | `0x45F7C` | BSS, including packet buffers |

Application compilation uses `-DETH_LOADER_ARA=1 -DETH_PROBE_USE_CDMA=1`
and `-Wall -Wextra -Werror`. Vendor BSP compilation separately emits the
previously documented lwIP checksum-offload helper warnings. This final XSA
reports TXCSUM/RXCSUM `None`; no warning suppression or vendor-driver edit was
used to make this build pass. Actual receive/transmit behavior still requires
the integrated board test.

The ROM guard in `ara_load.py` pins the packaged 8192-byte ROM SHA256:
`89c227ce79391eaf5a3dd21670e0cd5782b7736183679a2f2ba442b0db4a60fc`.
Disassembly review found LLC scratchpad initialization before the passive
loop at offsets `0x83A..0x88B`; the loop checks the scratch doorbell and UART.
The loader checks that exact live ROM, passive-loop PC, zero Ara-side DDR
history, zero traps and scratchpad configuration before accepting cold launch.
No UART debugger or second network writer may run concurrently. These guards
do not implement warm-cache invalidation or network authentication.

Outstanding launch gates are maintained in `../../ethernet/INTEGRATION_BATCH.md`.
