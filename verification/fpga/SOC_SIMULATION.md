# Candidate Whole-SoC Simulation Handoff

Status, 2026-09-22: the frozen candidate completed a full VCS SoC compile and
bare-metal smoke in `verification/out/soc-smoke-vcs-20260922-05/`. All reviewed
technology model checks passed. This is not Linux boot or board evidence. The
load-unit boundary contract and its host tests are separate evidence.

## Exact Inputs

```text
R = /home/wangwy/openproject/ara_dsa_verification
P = R/verification/out/fpga-soc-candidate-20260922-04/package
C = /home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara
```

`P/CANDIDATE_STATUS.md`, `P/manifest.json`, `P/SHA256SUMS` and
`P/provenance/verification_handoff/` identify the candidate, including repaired
PLIC/MMIO and the matched Linux bundle. Copied historical validation notes do
not sign off this candidate. Keep P, the original repository and C read-only;
future build/run outputs and reviewed simulation adapters belong in a new,
isolated directory with frozen source/model hashes.

## Top And Filelist

The shortest credible VCS path is a new thin bench around
`P/rtl/cheshire/hw/cheshire_soc.sv` (module `cheshire_soc`), with behavioral
memory on `axi_llc_mst_req_o/axi_llc_mst_rsp_i`. This retains CPU/Sv39, Ara,
interconnect, atomics, LLC, PLIC, CLINT and UART, but excludes board clocking,
the DDR wrapper/CDC and PHY. It is not DDR or FPGA timing validation.

- Use ordered `files`, `include_dirs`, and `defines` from sealed
  `P/manifest.json`; these are also rendered into `P/scripts/sources.tcl`.
  There is no packaged whole-SoC VCS recipe/filelist.
  Explicitly omit board-top/DDR sources and record technology-model substitutions.
  Do not regenerate a stock dependency list that loses the candidate fixes.
- Reproduce `board_cfg()` from `P/rtl/board/ara_dsa_vcu118.sv`: one hart,
  Ara enabled, four lanes, VLEN1024, RTC 1 MHz; SerialLink, USB, VGA, I2C,
  DMA and CLIC disabled. Other fields inherit the candidate `DefaultCfg`.
  Preserve `cv64a6_imafdcv_sv39`, `ARA`, `NR_LANES=4`, `VLEN=1024`, and
  the QBS/AKV/AKV-v2 feature defines. Match the DTB's 50 MHz system clock.
- Reuse components from `C/target/sim/src/`: `tb_cheshire_soc.sv`,
  `fixture_cheshire_soc.sv`, `vip_cheshire_soc.sv`, `tb_cheshire_pkg.sv`,
  and `elfloader.cpp`. Do not use them unchanged: stock Ara config is
  2 lanes/VLEN2048; VIP clocks default to 200 MHz/approximately 32768 Hz.
  Review JTAG timing for the candidate's SoC-clock-sampled TAP.
- `C/cheshire.mk:141` generates a Questa script selecting
  `cv64a6_imafdcsclic_sv39`; that is not this candidate's configuration.
  The generated compile script and referenced SPI/EEPROM models are absent.
  Passive boot does not need those external-device models.
- `R/hardware/Makefile` builds VCS top `ara_tb`, not Cheshire. Its
  `ara_system` ties external/software/timer IRQs low; its 1-64 MiB L2 cannot
  hold the supplied Linux layout. It is not the whole-SoC Linux route.

## Memory And Boot

Use `R/hardware/deps/axi/src/axi_sim_mem.sv`: sparse byte-addressed storage,
backdoor preload, no fixed dense 2 GiB allocation. Cheshire VIP already uses
it with `UseDramSys=0`; DRAMSys is unnecessary. Preserve upstream SoC atomic
handling because this memory model does not implement ATOPs. Match the external
map `[0x80000000, 0x100000000)`; LLC/SPM capacity is 128 KiB at `0x10000000`.

All payloads below exist in `P/linux/artifacts/`:

| Payload | Load address |
| --- | --- |
| `fw_jump.elf` | PT_LOAD segments at `0x80000000` and `0x80040000`; entry `0x80000000` |
| `ara_vcu118.dtb` | `0x80100000` |
| `Image` | `0x80200000` |
| `initramfs.cpio` | `0x88000000`; verified DTB end `0x88309200` |

Preload ELF segments with BSS zero-fill plus the three raw files. The simulation
initializes only the DTB's containing 4 KiB page to zero before placing its
original bytes; Linux scans the expanded FDT `totalsize` with `crc32_be`, and
otherwise-unused bytes must have deterministic values in the four-state sparse
DDR model. Other uninitialized DDR locations remain X. Reset enters
the included ROM at `0x02000000`; retain its LLC initialization. Passive
`boot_mode=0` supports UART WRITE/EXEC, or scratch launch: entry low/high at
`0x03000000/04`, then launch mask **2** at `0x03000008`. Existing JTAG VIP
also supports halt/load/DPC/resume. Prefer bulk backdoor loading followed by
the boot/debug launch, not serial transfer of the kernel. OpenSBI embeds the
matching DTB and jumps to the kernel; no U-Boot stage is required by this bundle.

Stock `+BINARY` handles one ELF and waits for bare-metal EOC, not Linux.
The new adapter must load raw payloads and use a bounded Linux boot criterion.
Use Cheshire `elfloader.cpp` with its VIP: Ara's `tb/dpi/elfloader.cc` has
incompatible DPI signatures. Keep firmware, external DTB and initramfs matched.

## IRQ Contract

PLIC is 58 slots, two contexts, `ndev=57`, base `0x04000000` (64 MiB window).
Context 0 drives M external IRQ/cause 11; context 1 drives S external IRQ/cause 9.
Source 0 is reserved; UART is 1, I2C 2-16, SPI 17-18, USB 19, GPIO 20-51,
and VGA/DMA/core bus-error sources 52-57. Disabled devices retain their IDs.
All slots are occupied by these internal sources: `intr_ext_i` is truncated
out of this configuration. Stimulate UART or GPIO, not a fabricated CPU IRQ.
UART is at `0x03002000`; CLINT at `0x02040000`, with 1 MHz RTC.
Observe source, claim/complete, M/S IRQ, trap and return, not just PLIC assertion.

## Tool And Model Requirements

VCS/Vlogan are on PATH under
`/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin`;
licenses were not checked. Host C++, `dtc`, `cpio`, `R/hardware/bender` and
cross-compilers are present. Existing payloads need no rebuild; the exact SDK
and OpenSBI overrides are in `P/linux/build_linux_bringup.sh`.

The RTL list contains Xilinx SRAM/XPM and clock cells; QBS instantiates `LUT5`.
Supply vendor simulation libraries or explicitly reviewed functional models,
not unresolved/black-box stubs. Local generic SRAM/clock sources and the LUT5
truth-table model in `hardware/fpga/vcu118/tests/check_qbs_fault.py` are reuse
inputs, not automatic equivalence signoff. Record latency, reset, read/write
semantics and exclusions for every replacement.

Full board top `ara_dsa_vcu118` additionally needs generated `clkwiz`, `vio`,
`ddr4`, UNISIM/XPM and a DDR4 device model. `P/scripts/create_ip.tcl` specifies
these IPs, but their generated assets are not packaged. Vivado and Questa were
not on the inspected PATH. This is a separate, longer path than SoC simulation.

## Remaining Gates

- Freeze and check the candidate configuration, compile inputs and reviewed
  models; a successful source/checksum audit is not elaboration or behavior PASS.
- Load-unit boundary results do not close real MMU/PTW/PMP, ACC translation
  ownership, load-return pipeline, scoreboard, flush or ID-reuse integration.
- Whole-SoC acceptance still requires actual M/S external-IRQ handling, Sv39
  translation/fault recovery, and OpenSBI/Linux reaching userspace with the
  matched bundle. Userspace RVV/context tests remain required; QEMU is not RTL evidence.
- No sparse-memory simulation signs off DDR calibration/CDC, reset/clocking,
  FPGA implementation/timing or board behavior. Custom QBS/AKV hidden-context
  isolation and native model execution remain separate gates.

Before a diagnostic run, freeze discriminating probes, pass/fail criteria and
a bounded trace/FSDB window. Analyze the capture before changing RTL or timing.
For runs expected to exceed ten minutes, use an independent background run,
confirm initial progress, and inspect after completion rather than polling.

## Isolated VCS Entry Point

`verification/fpga/run_soc_smoke.py` freezes the ordered candidate RTL,
include files, board configuration, technology models, AXI memory model,
bench, and existing `software/smoke.elf` into a new output directory. It
verifies selected package bytes against `SHA256SUMS`, refuses existing output
directories, and writes commands, logs and input hashes. The original package
and existing board/Linux workflows are not edited. This entry point defaults
to the bare-metal prerequisite. `--mode linux` selects the sealed firmware,
DTB, kernel and initramfs and requires OpenSBI, kernel, init and RVV userspace
milestones. It is still a SoC RTL simulation, not board or QBS/AKV model-level
signoff.

The VCS-only generated source copies move Cheshire's Ara AXI typedefs from a
generate scope, expand the zero-valued CVA6 ID-map default into its seven
two-element entries, and omit the Vivado-only `TARGET_VIVADO` define. The
sealed candidate RTL is unchanged. The bench uses a string format operation
for the decoded UART byte. The result reports VCS return code 0, technology
checks passed, a 153.617-second full-DUT compile, and a 98.2-second smoke
simulation. At 947,730 cycles the bench saw 3,800 ROM and 127,359 external-DDR
instruction retirements, 668 DDR read addresses, 4,362 DDR write addresses,
zero traps, two ROM UART acknowledgments, and the exact payload self-check
line. Inputs, the VCS executable and generated libraries, and the run driver
are hashed in `inputs.json`/`summary.json`. This smoke does not execute
QBS/AKV arithmetic or Linux. Warnings still require classification before
final signoff.

```sh
cd /home/wangwy/openproject/ara_dsa_verification
python3 -m venv verification/tools/soc-venv
verification/tools/soc-venv/bin/pip install -r verification/fpga/sim/requirements.txt
make -C verification fpga-soc-smoke SOC_SMOKE_OUT="$PWD/verification/out/soc-smoke-new"
```

Use a fresh name for every invocation. `--prepare-only` freezes and validates
inputs without invoking VCS; `--compile-only` stops after elaboration/build.
Default wall-clock limits are 30 minutes for compilation and three hours for
simulation. Runs expected to exceed ten minutes belong in a detached process
with its own driver log, not an interactive polling loop.

To run an already verified `--compile-only` directory once, use `--run-only`
with the same `--output`. It checks the frozen inputs and VCS executable,
snapshots the run-driver source, records hashes of the launcher and generated
shared libraries, and refuses to overwrite an existing `sim/` directory.

For a Linux payload-only change, `--mode linux --reuse-compiled-from <old-run>`
prepares a fresh output and copies a verified VCS image only when all compiled
RTL sources, include files, defines and entry address match. Runtime Linux
artifacts and `memory.hex` remain independent. Run the prepared output later
with `--run-only`; a diagnostic `--linux-cycle-milestone N` exits nonzero as
`LINUX_MILESTONE_REACHED`, never as Linux boot PASS. The original compiled run
and its evidence are not modified.

For a shorter diagnostic, `--linux-uart-milestone 'Linux version'` stops on the
first complete Linux UART version line, or use
`--linux-uart-milestone 'Ara verification Linux init reached'` to stop at init.
The result is `LINUX_UART_MILESTONE_REACHED`, not a boot PASS. Use one such
targeted run only when that marker answers the current question; full Linux
signoff still runs to the userspace PASS markers. The existing fail-fast and
no-progress guards can be combined with this option.

The boot plan is in `sim/BOOT_PROBE_PLAN.md`; supported memory and clock
semantics are in `sim/TECH_MODELS.md`. ELF loading uses `pyelftools` PT_LOAD
segments and explicit BSS zero-fill. No PC override, instruction substitution,
forced register value or fabricated peripheral completion is permitted.

The bench distinguishes ROM ACK, payload retirement, application self-check
success and Linux userspace. `SMOKE_PASS` is not a Linux result. The frozen
Linux image in `verification/out/soc-linux-vcs-20260922-01/` compiled and ran
for 17,290,291 cycles, but ended as `LINUX_BOOT_FAILED`. OpenSBI v1.7 appeared
on UART; the required Linux version and userspace markers did not. The first
`a_invalid_read_data` warning occurred at 10,219,890,000 ps. At
345,806,210,000 ps an active D-cache tag SRAM request had address `xx` and
the technology model correctly stopped the run. The last printed trap before
the fatal was an instruction page fault at PC `0x80201048`; temporal proximity
alone does not establish causality. No Linux PASS or model-level result may be
inferred from the 9.3 million retired instructions or the nonzero DDR traffic.

The tag SRAM address in `wt_dcache_mem.sv` is selected from `wr_cl_idx_i` when
`wr_cl_vld_i` is set, otherwise from `rd_idx_i[vld_sel_d]` when `rd_acked`
requests tags. A focused probe must record `vld_req`, `vld_addr`, `wr_cl_vld_i`,
`wr_cl_we_i`, `wr_cl_idx_i`, `rd_acked`, `vld_sel_d`, the selected `rd_idx_i`,
core PC/trap state and nearby cache/MMU responses at the first unknown address.
It must also capture the sampled D-cache data-valid/kill/data signals at the
earlier warning, since the warning's later `$display` value need not equal the
SVA-sampled value. This distinguishes a write-index X, read-index/arbiter X,
and an upstream translation or refill problem before any RTL change.
The optional `--cache-tag-probe` flag adds `+CACHE_TAG_PROBE` to a newly compiled
run and reports the first active unknown tag address and up to eight unknown
D-cache read-data samples. It is verification-only and disabled by default;
the probe run in `verification/out/soc-linux-cache-probe-20260923-01/` is
diagnostic, not a Linux pass criterion.

For a completed Linux run, `verification/fpga/check_soc_linux.py` independently
checks the run status, frozen inputs, VCS launcher/libraries, command, ordered
UART milestones and nonzero RTL activity. This checks evidence consistency;
it is not an architectural oracle for QBS/AKV computation.
