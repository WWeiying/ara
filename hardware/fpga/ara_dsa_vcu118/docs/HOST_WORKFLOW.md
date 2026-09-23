# Bare-metal host/debug/dual-DDR workflow

## Status and limits

This is an optional RTL and host-software implementation. Local digital tests
are not Vivado timing/CDC/DRC signoff and are not an FPGA pass. Build the `host`
profile first and complete stages 1 and 2 before building `dual_ddr`.

The existing baseline, COM6/115200 boot ROM, UART loader, Linux images and
QBS/AKV arithmetic are not replaced by this feature. An old bitstream cannot
expose these new debug cores. Do not infer that adding diagnostics fixes any
existing arithmetic or Linux boot fault.

Profiles have separate project directories and recorded synthesis state:

| Profile | Project suffix | Host/debug | Usable DDR |
| --- | --- | --- | --- |
| baseline | none | existing UART/VIO | C1, 2 GiB |
| host | `_host` | two JTAG AXI cores | C1, 2 GiB |
| dual_ddr | `_dual_ddr` | two JTAG AXI cores | C1+C2, 4 GiB |

Use the onboard USB-JTAG connector already used by Vivado. The external
J-Link/CPU TAP is not used by this loader. UART remains a separate optional
console connection. No new 1.8 V wiring or high-speed UART bridge is needed.

The two JTAG AXI cores serve different purposes:

- `gen_host.i_host_bridge.i_jtag_mem`: AXI4, 64-bit data/address, program/data
  loading through the Cheshire external-master port.
- `gen_host.i_host_bridge.i_jtag_debug`: AXI4-Lite, 32-bit data/address, direct
  access to the independent debug register bank, without the main fabric.

The debug bank survives a VIO reset; board reset, lost clocks, reprogramming or
power loss may clear it. VIO still resets the SoC **and MIG**. DDR retention and
CPU-only restart are not provided. Reset and reload before each execution.

## Build on Windows

Close Vivado GUI/workers before the managed build. Do not update sources while
a run is active. These short commands use the existing Vivado installation:

```powershell
cd D:\project\ara\hardware\fpga\ara_dsa_vcu118
powershell -ep Bypass -File .\scripts\create_profile.ps1 -Profile host
powershell -ep Bypass -File .\scripts\run.ps1 -Profile host -Stage all
```

The first command creates the separate project and synthesizes its required
vendor IP. It does not overwrite or upgrade the baseline project. The second
runs synthesis and routed implementation, retaining the existing failure
gates. Inspect timing, CDC, unconstrained paths and DRC before bit generation.
Use the `RunDir` printed by this run, never a guessed checkpoint path or a DCP
chosen by file size. Set `$run` to that printed directory, then use the wrapper:

```powershell
$bit = @{
  Profile = 'host'
  RunDir = $run
}
.\scripts\write_profile_bit.ps1 @bit
```

The default output is `bitstream_host` inside that run directory. It must not
already exist. Program the matching `.bit`/`.ltx` in Hardware Manager, not
configuration Flash. Use `Profile = 'dual_ddr'` for the later dual-bank build.

## 1. Debug and result collection

After programming the host profile, connect the board USB-JTAG. The snapshot
command does not reset, load, or execute the CPU. Each output directory must
be new, so prior evidence cannot be silently overwritten.

```powershell
cd D:\project\ara\hardware\fpga\ara_dsa_vcu118\software
$env:Path = 'D:\Xilinx\Vivado\2020.1\bin;' + $env:Path
$probes = 'D:\fpga_runs\ara_20260923_125216_228b9d4f9525\bitstream_host\ara_dsa_vcu118.ltx'
py -3 .\host_load.py snapshot --probes $probes --out D:\fpga_host_runs\snapshot01
```

Replace `$probes` with the `.ltx` from the same output directory as the bitstream
currently programmed on the board. The loader opens its own Vivado session, so
the GUI's probes-file setting is not inherited. Its log lists every detected
JTAG AXI object before matching the expected core names.

Outputs include `report.json`, `snapshot.json`, `snapshot.csv`, a Vivado log,
and a transaction audit log. A collected snapshot is **not** an execution pass.

If `load` stops at the AXI burst-mapping preflight, first check whether a
single-beat write to the second address works. After a full VIO reset and
with the GUI hardware target disconnected, run:

```powershell
py -3 .\host_load.py axi-probe --probes $probes --full-reset-confirmed --out D:\fpga_host_runs\axi_probe01
```

This probe does not load or launch an ELF. It saves two 64-bit words in the
reserved DDR1 scratch area, writes only the second word, reads both addresses
separately, then restores and verifies both. Inspect `axi_single_beat_probe`
in `report.json`: `verified=true` rules out a basic single-beat write failure
at the second address, but does not establish that AXI bursts work. If
`restored=false`, do not treat the scratch contents as preserved.

If the single-beat probe passes but the original two-beat preflight fails,
run one format-discriminating test after another full VIO reset:

```powershell
py -3 .\host_load.py axi-burst-probe --probes $probes --full-reset-confirmed --out D:\fpga_host_runs\axi_burst01
```

It first compares a two-beat read with separate reads, then uses the
word-separated two-beat write syntax shown in Vivado documentation. It reads
both addresses separately and restores them with single-beat writes. The
`axi_burst_probe` object in `report.json` distinguishes read-burst failure,
word-separated write failure, and successful scratch restoration. This is a
diagnostic A/B test, not permission to skip the normal load preflight.
If the read comparison fails, no write is attempted; the probe records a
repeated burst, ten neighboring single reads, and a burst starting at `+8`
to distinguish stable address-dependent data from a transient return value.

The register bank records cycles, retired instructions, last retired PC,
commit-head PC, last committed exception PC/cause/tval, software marker/run ID,
result and done. A configurable no-retirement watchdog freezes and snapshots
measurements; it does **not** halt/abort the CPU. It is disabled by default,
since long accelerator instructions or WFI can legitimately stop retirement.

For each DDR path, counters observe accepted requests/responses and stalls at
the 64-bit LLC output, before MIG width conversion:

- AR/AW transaction counts, outstanding reads/writes, last AR/AW addresses.
- R bus-occupancy bytes: 8 per accepted R beat, not narrow requested bytes.
- W payload bytes: accepted `WSTRB` population count.
- AR/AW/R/W valid-without-ready cycles and B/R error-response counts.
- Last error response type and ID. There is no response-to-address tracker;
  last AR/AW addresses must not be called the failing address.

These are not DDR PHY traffic, power, energy, QBS coverage or logits accuracy.
Use software mailbox words for operation counts/numerical checks; use external
power measurement for J/token. Commit-head PC is a raw pipeline observation,
not proof that the instruction at that address is the root cause of a stall.

All 64-bit hardware counters are copied into one stable snapshot at one clock
edge. Host collection validates the snapshot sequence before and after reads.
Software mailbox fields are live and should be consumed only after done.

## 2. Load and run without Linux

First use `host_smoke.elf`, a small scalar-only memory/result test, not Qwen and
not an accelerator performance claim. Prebuilt ELFs are included so Windows
does not need a RISC-V compiler.

1. Apply a full VIO reset, release it, and wait for the existing VIO status
   word to become `1110`. Keep boot mode `00` (passive ROM).
2. Do not run `uart_load.py` or send the UART ACK handshake. Once ROM enters
   its UART server it stops polling the JTAG scratch launch flag.
3. Close the GUI connection to the hardware target before the host command.
   Merely closing a connection is not a board reset.
4. Execute this array-based command. No individual quoted item spans lines:

```powershell
$load = @(
  'load'
  '--probes'
  $probes
  '--elf'
  '.\host_smoke.elf'
  '--full-reset-confirmed'
  '--out'
  'D:\fpga_host_runs\smoke01'
)
py -3 .\host_load.py @load
```

The confirmation flag is an assertion that you actually reset the board; it
does not reset hardware. The loader checks identity/capability/readiness and
passive boot registers, loads ELF `PT_LOAD` segments plus zero-filled BSS,
reads back and hashes each segment, then publishes the 64-bit entry and writes
`2` to scratch register `0x03000008` last. Bursts are at most 256 beats and do
not cross 4 KiB. Unaligned image edges preserve neighboring bytes.

Only a matching run ID, nonzero done, zero software result, valid retirement
measurement and no recorded hardware errors can produce an execution pass.
Timeout, empty results or AXI errors produce a nonzero exit and failure report.
On a memory-transport failure a fresh debug-only session attempts a snapshot;
it does not attempt to resume a possibly partially loaded program.

`host_trap.elf` deliberately executes an illegal instruction. It is a negative
test: expect failure status, a trap marker and captured cause/PC, not PASS.

For existing bare-metal benchmarks, include `fpga_debug.h` only in a build
intended for a host-enabled bitstream:

```c
fpga_debug_begin();
/* Run work; wait for accelerator completion and drain output stores. */
fpga_debug_marker(stage_id);
fpga_debug_finish(numerical_check_failed ? 1 : 0);
```

The measurement window is delimited on the FPGA, not by slow host polling.
It includes small instrumentation overhead. Measure an empty window when
reporting very short kernels. The helper does not itself wait for QBS/AKV.
Legacy ELFs without the done/result protocol can still use UART, but cannot
be reported as passing by this host runner. Cache-enabled repeat execution
without reset is not supported: external writes do not snoop private L1D.

The report separately records verified loading time and payload bytes/second,
including readback. Measure a representative payload before transferring a
large model. JTAG/Tcl overhead can dominate; no speedup factor is assumed.
The UART 115200 8N1 theoretical ceiling is 11,520 bytes/s, not a measured
baseline. This change does not implement Ethernet or PCIe.

Optional UART capture runs separately and never transmits a loader handshake:

```powershell
py -3 .\host_load.py uart --port COM6 --out D:\fpga_host_runs\uart01
```

## 3. Enable and validate C2

Only after the host-profile checks pass, repeat the build with
`-Profile dual_ddr`. This is a new bitstream; software alone cannot add C2.
Set `$probes` to the matching dual-DDR `.ltx` after programming that bitstream.

| Bank | Physical address range (end exclusive) |
| --- | --- |
| C1 | `0x80000000 .. 0x100000000` |
| C2 | `0x100000000 .. 0x180000000` |

The existing AXI crossbar implementation selects the channel using the full
address before each wrapper truncates to 31 local address bits. It retains
same-ID ordering/AW-W association and rejects unmapped addresses. Legal AXI
bursts must obey the 4 KiB boundary rule. Both CDC halves are reset if either
DDR channel loses readiness. C1 and C2 both must calibrate before SoC release.

Perform a full VIO reset. The destructive scratch test overwrites the last
64 KiB in each bank. Do not run it against a live program/model:

```powershell
$test = @(
  'ddr-test'
  '--probes'
  $probes
  '--full-reset-confirmed'
  '--destructive-ddr-test-confirmed'
  '--out'
  'D:\fpga_host_runs\ddr01'
)
py -3 .\host_load.py @test
```

Then reset again and load `host_ddr2_smoke.elf` using the stage-2 command. This tests
CPU accesses above 4 GiB with distinct same-offset canaries in both banks.
The JTAG scratch test checks host access and cross-bank aliasing. The CPU
smoke writes and reads cacheable addresses on the same core; its PASS alone
does not prove that a CPU write reached physical C2. Confirm independent
CPU-originated C2 traffic and readback with a cache-aware board test before
claiming the CPU C2 path works. These are small bring-up tests, not an
exhaustive 4 GiB memory/stress test.
The original UART loader keeps its original single-bank address limits.

Two banks increase addressable capacity, not automatically bandwidth. The
common 64-bit/50 MHz SoC port has an ideal 400 MB/s per-direction beat rate;
actual traffic is lower. Benchmark both-bank traffic and long-running memory
integrity on the board before publishing performance results.

## Reproducibility and references

`hardware/fpga/vcu118/integrate_host.py` applies only these feature templates
to the existing exported package. It avoids a full re-export of unrelated
CPU/Ara fixes. Profile tests, debug-register simulation and dual-DDR digital
tests live under `hardware/fpga/vcu118/tests`.

Vendor interfaces and physical assumptions must be checked in Vivado/board
bring-up: [JTAG AXI PG174](https://docs.amd.com/v/u/en-US/pg174-jtag-axi),
[HW_AXI properties UG912](https://docs.amd.com/r/2023.2-English/ug912-vivado-properties/HW_AXI),
[VCU118 UG1224](https://docs.amd.com/v/u/en-US/ug1224-vcu118-eval-bd).
