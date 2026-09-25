# J10 Ethernet-to-DDR loader: implementation status

## What passed on 2026-09-25

- `loader_preflight.tcl` ran in an isolated Vivado 2020.1 project on the
  Windows FPGA workstation. Its successful evidence is
  `D:/fpga_runs/ara_loader_preflight_20260925_05`.
- The local catalog contains AXI Ethernet 7.2, AXI DMA 7.1, MicroBlaze 11.0,
  SmartConnect and DDR4. The VCU118 board part was accepted.
- AXI Ethernet accepted SGMII/LVDS VCU118 settings with
  `CONFIG.processor_mode=true`. AXI DMA accepted scatter/gather, 32-bit
  receive/transmit streams, a 64-bit S2MM memory bus and 32-bit addresses.
  Both IP output targets were generated. The license-status report lists
  `tri_mode_eth_mac` Synthesis as `Bought`/`Bought`; bitstream license use has
  not been tested for this new configuration.
- The existing diagnostic image uses `processor_mode=false`. That mode has no
  processor driver support, so its PHY/PCS configuration can be reused but
  its MAC configuration cannot be connected to lwIP unchanged. See
  [PG138 processor mode](https://docs.amd.com/r/7.2-English/pg138-axi-ethernet/Functional-Description).
- The Python sender and hardware-independent C receiver passed native unit
  tests, including Python-to-C pipe and real localhost TCP exchanges with
  the actual `host_smoke.elf`. Fragmented handshake, bad payload CRC and
  mid-record disconnect were exercised. The TCP adapter has a lwIP socket
  build path checked with a native shim forcing short sends/receives, not real
  lwIP/BSP headers; no board
  BSP exists to compile/link it yet. These tests use
  simulated memory, not the FPGA. The C receiver also compiled without
  warnings using Vitis 2020.1 `mb-gcc` on Windows. The sender's `--plan-only`
  mode parsed the real `host_smoke.elf` into 448-byte and 4352-byte DDR1
  segments, with the latter including BSS zero fill.

## Candidate wire contract, not yet a board protocol

`ara_dsa_vcu118/software/eth_load.py` reuses `host_image.prepare_image` for
RV64 ELF and raw segment validation. After TCP connection the client sends
eight ASCII bytes `ARAETH01`. The receiver returns little-endian
`<8sII>`: the same magic, capability bits, and maximum block size (1..65536).
Only DDR1 capability is implemented in the C receiver.

Each record is little-endian `<4sQII>`: `DATA` or `DONE`, DDR address or
entry, byte count, and payload CRC32. `DATA` is followed by payload bytes.
The receiver checks length, DDR1 bounds, monotonic non-overlap, received CRC,
then writes and reads back DDR before replying with `<QII>`: address,
readback CRC32, status. Any mismatch aborts the connection. `DONE` has zero
length/CRC and only acknowledges completed transfer; **it does not boot Ara**.
The host report's transfer rate includes per-block peer readback acknowledgments.

The intended software base is the Vitis 2020.1 FreeRTOS lwIP TCP performance
server in `D:/Xilinx/Vitis/2020.1/data/embeddedsw/lib/sw_apps/` with its
socket-mode API. `firmware/eth_loader_tcp.c` now supplies exact-length socket
I/O for the shared receiver and was tested through native BSD sockets; the
actual lwIP branch and FreeRTOS task still require an XSA/BSP. The remaining
custom code is the physical DDR memory callback and eventual boot handoff;
the TCP stack, MAC driver and DMA remain Xilinx components. This board
integration has **not** been built or tested.

## Required before programming a loader image

1. Build an isolated processor-mode J10 + DMA + MicroBlaze + DDR system with
   valid clocks/resets, driver BSP and a reserved location for MicroBlaze code,
   descriptors, stack and heap. Do not let an Ara image overwrite them.
2. Prove real DDR write and physical readback through that system. A cache-hit
   CRC is not evidence of DDR content; flush/invalidate or disable cache as
   appropriate before readback. Run timing, DRC and CDC checks.
3. Integrate with Ara's passive ROM and verify that network loading does not
   reset the DDR. The existing full VIO reset resets MIG and destroys the
   newly loaded image. The JTAG multi-beat read anomaly also means the old
   host path cannot be assumed safe for DMA bursts.
4. Only then run smoke, larger payload, corruption, reset/retry and sustained
   throughput tests on board. The measured echo RTT is not a download rate.

No bitstream, throughput result or board-level DDR result exists for this
downloader yet. The currently programmed board image remains the J10
diagnostic echo image.

Local tests (no hardware):

```sh
python3 -m unittest hardware/fpga/vcu118/tests/test_eth_load.py -v
cc -std=c11 -Wall -Wextra -Werror -o /tmp/eth_loader_core_test hardware/fpga/vcu118/ethernet/firmware/eth_loader_core.c hardware/fpga/vcu118/tests/eth_loader_core_test.c
/tmp/eth_loader_core_test
```
