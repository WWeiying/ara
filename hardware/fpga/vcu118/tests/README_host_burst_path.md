# Host Burst Path Isolation

## Question

Board reports show successful independent 64-bit accesses but incorrect second
beats of INCR reads at both DDR scratch (0xffff0000) and the nominal LLC SPM
alias (0x1401ff00). Later live DDR counters show the latter actually reached
DDR1 on the programmed image; it was not an independent SPM-path check.
Resetting JTAG AXI and refreshing its transaction data did not change the
reported failure. These were initially user-reported board
observations; the subsequent read-only map and partial netlist were uploaded
on `fpga-evidence/axi-20260924_045820-8ac2da54` and verified locally.

The hypothesis tested here is that the common RTL interconnect drops or
misaddresses beats under consecutive transfers or read backpressure.

## Test Boundary

`host_burst_path_tb.sv` instantiates the exported FPGA package's AXI crossbar,
RISC-V atomic adapter, post-adapter cut, SPM alias remapping and LLC. Geometry
is 8 ways x 256 lines x 8 blocks, with 48-bit addresses, 64-bit data and host
input index 3. Other masters are idle; non-memory outputs are unused.

The bench follows the boot ROM's BIST wait and all-SPM configuration writes.
In this simulation, DDR then takes the LLC bypass; SPM accesses exercise LLC
data storage. This simulated routing does not establish the programmed board's
route for the nominal SPM alias. The SRAM
implementation is the existing generic `tc_sram` simulation model. The production
`dram_wrapper_xilinx` supplies data/ID conversion, CDC, address slicing and UI
reset logic. A test-only `ddr4` AXI endpoint uses the library `axi_to_mem` adapter
and a sparse 512-bit array. It has a separate approximately 300-MHz clock and
periodic backpressure; it does not simulate vendor MIG or the physical DDR bus.

The bench checks single writes followed by burst reads, burst writes followed
by single reads, consecutive and throttled RREADY, 1/2/3/16/256-beat
transactions and SPM cache-line crossings. Transfers adjacent to a 4 KiB boundary are
separate legal transactions, not an AXI burst crossing that boundary.
Data depends on address and write epoch. It checks RLAST, RID, RRESP, BRESP,
ARADDR/ARLEN/ARSIZE/ARBURST propagation, accepted beat/transaction counts,
and response stability at the LLC and host during backpressure.

## Run

From the repository root, with a working Verilator installation:

```sh
python3 hardware/fpga/vcu118/tests/check_host_burst_path.py /tmp/host_burst_new
```

Use a new output directory each time. `--verilator` accepts an explicit tool
path. On this host the relocated installation needs its matching data root
and the binary entry point:

```sh
env VERILATOR_ROOT=/home/wangwy/software/toolchains/verilator/share/verilator \
  python3 hardware/fpga/vcu118/tests/check_host_burst_path.py /tmp/host_burst_new \
  --verilator /home/wangwy/software/toolchains/verilator/bin/verilator_bin
```

The runner records source/header hashes, tool version, command and outcome in
`result.json`, compiler diagnostics in `compile.log`, and cycle-stamped boundary
transactions in `run.log`. Compilation and simulation have bounded deadlines.
The exported RTL is unchanged. Compiler warnings remain in the log; this test
is not a lint/DRC signoff. `ENUMVALUE` is disabled for the exported tag-store's
zero initialization of an enum-bearing structure; runtime assertions are on.

## Measured Result

Extended-chain evidence: `/tmp/ara_host_chain_final_01`. A subsequent focused
run added FIXED reads at `0x1401ff00` and `0x1401ff38` after single-word writes.
Those reads repeated the starting word on every beat through the crossbar and
SPM LLC path:

```text
PASS: host burst path checked_beats=2297 read_transactions=626 stalled_cycles=3383 cycles=35487
```

Focused-run evidence: `/tmp/ara_host_fixed_spm_20260924`. A separate attempt
to use FIXED reads at `0xffff0000` found that the test-only DDR `axi_to_mem`
endpoint returned zero after the first beat; it cannot validate FIXED burst
semantics of the physical MIG. That failed attempt is retained at
`/tmp/ara_host_fixed_probe_20260924`. Neither simulation exercises the Xilinx
JTAG core or the physical MIG narrow-burst setting. The board's FIXED read
matched the next 64-byte line at both addresses. Subsequent ARCACHE and DDR
counter probes instead point to a disabled narrow-burst setting on the 512-bit
DDR interface; see [the board mapping](README_host_burst_read_map.md).

This does not reproduce the board failure. It does NOT validate the Xilinx
JTAG core, Tcl/JTAG transfer packing, XPM/URAM implementation, MIG internals,
physical timing/metastability, multi-master contention or CPU execution. It does not
justify declaring the burst loader fixed. The DDR IP parameter change still
requires a fresh bitstream and board regression.

The earlier low-cost discriminator was the complete `neighbor_single_bytes`
array already recorded in the Windows `axi_burst02/report.json`: compare the
unexpected second 8-byte word with all recorded adjacent single reads. A
match at another offset is evidence for an address/stride investigation,
not proof of the failing component. No match does not prove stale data.

The user subsequently expanded that array: `1032547698badcfe`, the unexpected
second read beat, matches the single read at `0xffff0048`, not `0xffff0008`.
It also matches the second test word in the earlier burst-write preflight.
This supports investigating burst address mapping; it does not establish a
constant 72-byte stride or identify a faulty RTL/IP block. The earlier
`restored=true` check covered only the two intended single-word addresses,
not the possible side effect at +0x48.

`host_burst_read_map.py` is a read-only board discriminator. Run it from the
exported software directory with positional arguments matching LTX and a new
output directory. It uses the existing transport/identity check and gathers
32 single reads before and after varied 2/3-beat reads in each of DDR scratch
and SPM. It saves raw results, every matching address (not just the first),
window stability and partial failures to `map.json`. It neither resets nor
launches the CPU, changes constraints, nor writes memory/debug registers.
Close the GUI target connection first and do not run concurrent board tests.
Unstable windows, repeated values and words with no match remain ambiguous;
even a stable before/after window cannot rule out intervening modifications.

Six mock tests in `test_host_burst_read_map.py` pass for normal mapping,
72-byte stepping, unmatched stale data, duplicates, changing memory and
failure evidence retention. These test the diagnostic, not board behavior.

See [the end-to-end audit](README_host_chain_audit.md) for the current evidence
matrix, source/probe semantics and the outstanding full-netlist boundary.
