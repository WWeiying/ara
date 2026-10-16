# Ara integration preparation

Status: shared-DDR RTL, matching firmware and the `host_ethernet` profile are
frozen and the combined flow has been launched. Synthesis, timing and board
acceptance are not yet established. See `INTEGRATION_BATCH.md` for the run.
The accepted
standalone baseline transfers 256 MiB twice at 9.969/9.949 MB/s with DDR
readback, zero retries and independent JTAG checks; see `LOADER_STATUS.md`.
That result does not establish integrated throughput or program execution.

## First acceptance target

Load `host_smoke.elf` over J10 into Ara C1 DDR, verify it, start it through the
existing JTAG/passive-ROM path, and require a fresh run ID, done=1, result=0,
no trap and no memory errors. Keep USB-JTAG for initialization, launch and
diagnostics; Ethernet carries the large payload. Do not require an Ethernet
launch protocol, operating system or dual-DDR integration for this milestone.

## Source audit and selected starting point

Paths below are relative to `hardware/fpga`.

| Boundary | Current source/evidence | Integration work |
| --- | --- | --- |
| Ara DDR | `ara_dsa_vcu118/rtl/board/dram_wrapper_xilinx.sv`: 512-bit MIG, 31-bit bank address, 8-bit ID | Share the existing C1 MIG; remove standalone loader MIG |
| Ara clock | `ara_dsa_vcu118/scripts/create_ip.tcl`: 50 MHz | Keep its clock; loader remains 100 MHz with explicit CDC |
| Loader | `vcu118/ethernet/loader_bd_build.tcl`: MB, AXI Ethernet, SG DMA, CDMA, SmartConnect | Export loader memory traffic, readiness and shutdown control |
| JTAG memory | `ara_dsa_vcu118/rtl/board/ara_dsa_vcu118.sv`: external master through Cheshire/LLC | Retain for control; avoid duplicating its internal ID namespace |
| Reset | Board top VIO drives `sys_rst`, including MIG | Full reset before load only; restore MB firmware after reset |
| Launch | `software/host_load.py:load_and_run` and reference Boot ROM | Entry at `0x03000000`, doorbell value 2 at `0x03000008`, written last |
| Build profiles | `scripts/config.tcl`: includes host_ethernet | Finish vendor BD packaging and matching firmware before a combined build |

Selected integration boundary: existing repository `axi_mux` and `axi_id_remap`
at the C1 MIG UI AXI input, with `axi_isolate`, `axi_demux` and `axi_err_slv`
on the loader path. Both inputs are already 512-bit and in the UI clock domain.
The generated loader SmartConnect provides width/clock conversion and an
ID-less 32-address/512-data master. It restores its upstream IDs internally;
the adapter supplies ID zero. The shared mux adds a master bit and remaps
9-bit IDs back to the MIG's 8 bits, without truncation. Preserve the existing
MIG R-channel cut after arbitration and preserve one physical DDR controller.

The loader uses global addresses `0x80000000..0xffffffff`; MIG uses bank
offsets `0..0x7fffffff`. Reject out-of-range requests before subtracting the
base or dropping address bit 31. Do not rely on truncation for protection.
Separate address decoding for MicroBlaze MMIO from the DDR export. Preserve
the loader's established DMA descriptor and packet-buffer access to DDR.
The generated interface has passed isolated Vivado BD validation. The shared
RTL passed a bounded VCS protocol test, including same IDs on both masters,
backpressure, burst/strobe correctness, address rejection and drain-before-lock.
No combined synthesis/implementation netlist has been accepted yet.

This connection bypasses the LLC. The current DDR observers sit upstream on
Ara's LLC output and will not count loader traffic. Add loader-side accepted
AW/B and AR/RLAST/outstanding/error visibility; do not call the old DDR
snapshot a complete monitor of Ethernet transactions.

## Proposed address contract

All ranges are half-open. The offline preparation tool, integrated firmware
and `ara_load.py` now enforce the application limit. Standalone firmware keeps
its existing limit and is rejected by the integrated sender's INFO handshake.

| Use | Begin | End | Size |
| --- | --- | --- | --- |
| Application ELF/BSS/raw data | `0x80000000` | `0xFEFF0000` | 2031.9375 MiB |
| JTAG/shared-memory diagnostics | `0xFEFF0000` | `0xFF000000` | 64 KiB |
| Loader BSS, packet buffers, descriptors | `0xFF000000` | `0x100000000` | 16 MiB |
| MicroBlaze local BRAM, separate address space | `0x00000000` | `0x00080000` | 512 KiB |

The existing JTAG preflight address `0xFFFF0000` CONFLICTS with loader-private
DDR. The integrated sender never invokes that preflight; any future shared
diagnostic must use the designated diagnostic range. The existing
standalone sender/firmware permit writes up to `0xFF000000`. Do not launch the current
`host_load.py load` after Ethernet loading: it performs its own preflight
and reloads the image. `ara_load.py` instead uses the common launch helper
only after its own network verification and lock/drain checks; it exposes no
unchecked "skip verification" option.

Linux must later exclude both reserved regions through its memory map or
device-tree reservation. Merely protecting network writes does not prevent
the Linux allocator or a bare-metal program from overwriting loader memory.
The first integrated Linux attempt limits the DTB memory size to
`0x7EFF0000`, excluding both regions, and uses `ara_load.py --linux --port`
to require a UART init marker rather than a bare-metal debug-done record.
See `ara_dsa_vcu118/linux/README.md` for its incomplete board result.

## Reset, cache and launch sequence

1. Start from full board/SoC reset or new programming, select passive boot
   mode 00, wait for MIG calibration and both clock-domain resets to release.
   DDR and loader firmware must be initialized after this reset.
2. Identify the integrated build and matching firmware, confirm passive ROM
   and scratch[2]=0. The CPU is running ROM, not held in reset. Audit the
   actual packaged ROM/LLC initialization to establish that it has not touched
   the application range. Reference ROM C/assembly alone is not binary proof.
3. Check all ELF/BSS/raw ranges before sending. Admit payload writes only
   during loading. Keep a session/image identity across load and launch.
4. Finish every segment with exact readback, then set the sticky UI-domain
   hardware admission lock. `axi_isolate` drains accepted AW/W/B and AR/RLAST
   before asserting isolated. Require a stable locked+isolated status, balanced
   loader AW/B and AR/RLAST counters, and zero errors before launch. Requests
   still upstream of isolation may stall but cannot access DDR. Do not reset
   DMA while transactions are being drained. An END packet or unplugged cable
   is not a drain ACK. Integrated software orchestration has mock/unit tests;
   its board validation remains pending.
5. The standalone firmware accepts another BEGIN after END. Hardware isolation
   prevents such traffic reaching DDR after lock; lock cannot clear until a
   full UI reset. Do not treat firmware END as sufficient protection.
6. Require the cold-cache contract before launch. DMA writes bypass LLC and
   CPU caches. `fence.i` is not an LLC invalidation operation. If the CPU/LLC
   has touched the target range, abort this first-version attempt and reset
   before reloading; later warm reload needs explicit cache maintenance.
   JTAG verification before launch must not introduce dirty application lines.
7. Initialize fresh debug run controls; write and read back the 64-bit entry
   at `0x03000000`; check ready and quiesced status again. Write doorbell 2
   at `0x03000008` last, preserving scratch[3] for the 64-bit JTAG beat.
   Boot ROM source tests `scratch[2] & 2`, which is bit 1 despite old comments.
8. Require the matching run ID and smoke completion/result; collect CPU traps
   and both Ara/loader memory errors. Do not assert VIO reset after loading.

## Clocks, pins and implementation gates

- Ara and the standalone loader both use E12/D12, the board's 250 MHz clock.
  Share the existing top-level IBUFDS. Do not instantiate two input buffers or
  paste both top-level clock constraints for those pads.
- Share the L19 reset input. J10 uses AT22/AU22 reference clock,
  AU21/AV21 TX, AU24/AV24 RX, AR23 MDIO, AV23 MDC and BA21 PHY reset, as
  recorded in the accepted `constraints/loader_pins.xdc`. Remap port names
  and inspect generated IP constraints for duplicate assignments.
- Clock the loader at 100 MHz, preserve Ara's 50 MHz target, and synchronize
  readiness/quiesce controls separately from AXI payload CDC. A fabric reset
  must not erase DMA bookkeeping while transactions remain outstanding.
- The current host-profile IP script enables MIG narrow bursts. Verify the
  actual generated XCI property; an archived pre-fix DCP is not evidence.
- Create an immutable source snapshot and separate build/run directories.
  Run focused shared-DDR tests for simultaneous masters, backpressure, IDs,
  unaligned strobes, 4 KiB splits, invalid addresses, reset and drain. Include
  a negative test showing stale cache behavior is not accepted as success.
- Then run top-level synthesis, implementation, timing including bus skew,
  DRC, CDC and unconstrained-path review before bitgen. Account for new DMA
  errors and any changed timing paths; prior standalone signoff does not
  transfer to the combined design.
- Board progression: identity/calibration, guarded shared-DDR read/write,
  Ethernet smoke load plus JTAG execution, trap result, vector smoke,
  256 MiB sustained transfer, finally Linux. Re-measure integrated throughput.

## Offline preparation command

From the repository root on Linux:

```sh
python3 hardware/fpga/vcu118/ethernet/prepare_ara_integration.py --out /tmp/ara_eth_preparation
```

On Windows:

```powershell
py -3 D:\project\ara\hardware\fpga\vcu118\ethernet\prepare_ara_integration.py --out D:\fpga_runs\ara_eth_preparation
```

Use a fresh output directory. Optional `--elf` and repeated `--load ADDRESS:FILE`
reuse the existing ELF parser, overlap/BSS checks and source hashing. Outputs
are `plan.json` and `sources.zip`, a selected source/reference snapshot, not
a standalone build package. The report always says launch is disallowed and
integration is not validated. It invokes no Vivado, network access or board
commands. Archive matching bitstream/LTX/ELF/XSA hashes and BSP/linker metadata
alongside this report before building; do not assume Git HEAD captures the
many currently uncommitted Ethernet sources.
