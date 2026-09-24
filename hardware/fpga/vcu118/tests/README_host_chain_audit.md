# Host AXI End-to-End Audit

## Disposition

Burst mode is NOT accepted and the root cause is NOT identified. The supported
board evidence is the explicit single-beat load/readback/launch workflow. Do not
remove the burst mapping preflight, reorder returned data to hide a mismatch,
or change RTL/timing constraints based on the data-match pattern alone.

This audit uses source revision `ac28c00d`, the archived evidence commit
`62abf7054a0876f9924e5cebd2246ddd182e5788`, and the additional local tests below.
The package's RTL, `scripts/create_ip.tcl`, and constraints have no Git diff
between `7556343f` and `ac28c00d`. This reduces source-version ambiguity; it is
not an independent proof that those sources generated the running bitstream.
The package's entire `SHA256SUMS` verification passed.

## Evidence Identity

- Uploaded branch: `fpga-evidence/axi-20260924_045820-8ac2da54`.
- Archive SHA256: `cb8d0d2b4c0221ce7017724f375ac649b36269e4f35c39de1a09311940eaf63c`.
- Ten archive members were checked against the upload manifest, including sizes.
- Windows inspection records routed DCP SHA256
  `cba09318d878dea5325d08b1ba53c55559e49def20bb282b764807cb264272ac`.
- The DCP itself and whole-design functional netlist have NOT been received.
- Local board evidence: `/tmp/ara_axi_evidence_5BlYOLNe`.

The DCP and LTX checks tie the offline export to `bitstream.json`. They cannot
attest which image is physically programmed at a later live diagnostic session.
The burst map and netlist were collected at different times. No live AR/AW or
R/W waveform was captured. A functional Verilog export cannot prove timing.

## Reconstructed Path

```text
ELF/raw bytes -> host_image -> host_load -> Operation -> local socket batch
 -> host_vivado Tcl -> JTAG AXI command/response FIFOs
 -> ara_host_bridge (64-bit data, 48-bit SoC address, 2-bit ID)
 -> host xbar input 3 -> LLC output (4-bit ID)
 -> RISC-V atomics -> axi_cut -> SPM alias remapping -> LLC
    -> SPM: splitter -> descriptor/tag/control -> read/write unit -> XPM/URAM
    -> DDR: LLC bypass/cache path (5-bit ID)
       -> 64-to-512 data converter -> 5-to-8 ID extension
       -> five-channel Gray-pointer CDC -> 31-bit address -> MIG AXI -> DDR
 -> matching return path -> JTAG response FIFO -> Tcl DATA -> Python bytes
```

The dedicated 32-bit JTAG debug AXI-Lite core takes a separate route to the
local debug registers. Its successful snapshots do not validate memory bursts.
The sampled external CPU JTAG pad and Vivado's built-in JTAG AXI IP are distinct
interfaces; pad timing constraints are not evidence for the latter's commands.

## Stage Review

| Stage | Checked semantics and evidence | Remaining boundary |
| --- | --- | --- |
| Image | RV64 little-endian ET_EXEC, physical/virtual identity, DDR range/capability, overlap, executable entry, BSS zero fill and SHA256 | Arbitrary payload execution is not tested by loading a blob |
| Chunking | 8-byte alignment/RMW, max 256 beats, no 4-KiB crossing; explicit single-beat mode never sends a multi-beat memory operation | Existing burst safety probe tests a small scratch region, not every address |
| Packing | Lowest-address little-endian word on right; strict hex width; known-vector tests; raw Vivado DATA already contains wrong second word | No claim that these conventions work across all Vivado versions |
| Socket/batching | Ordered operations; sequence/index/status/END checks; no queued asynchronous Vivado transaction mode | Python mocks cannot validate vendor IP |
| Tcl/JTAG | Unique normalized CELL_NAME/protocol selection; CMD.LEN/SIZE/BURST checks; refresh, completion and response checks; no automatic reorder | CMD.SIZE=64 is a tool property, not a sampled physical AxSIZE=3 |
| IP configuration | Source says AXI4 Full, data/address 64, ID 2, queues 16; netlist confirms port widths | Actual AxSIZE is driven by command FIFO FDREs, not constants; `???` is not observed X |
| Bridge | Direct len/size/burst/data handoff; AWATOP/user/region zero; only high address bits truncated | Complete physical net connections not yet available |
| Xbar/atomics/cut | Correct address/len/size/burst/ID handling in static inspection and integrated RTL simulation | Only host master active; not full-system contention or archived gates |
| SPM alias | 0x14000000 maps to 0x10000000, preserving low 26 bits | Cannot infer live LLC configuration solely from the boot ROM source |
| LLC control | 64-byte lines; cutter splits at line boundaries; read/write units advance only on accepted requests | Local cell exports lose some duplicate aliases/constants; complete connectivity still needed |
| SRAM/XPM | Data-way address is `{line_addr, blk_offset}`; byte-enable mapping, request enable and latency checked in source | Generic SRAM tests do not validate actual XPM/URAM or its physical mapping |
| DDR conversion | Actual production wrapper, 64-to-512 converter, ID extension, CDC, 31-bit address slice exercised end-to-end | Modeled MIG AXI endpoint, not vendor MIG/DDR PHY |
| Return channels | Address-dependent data, RLAST/RID/RRESP/BRESP, accepted counts, R stability under backpressure tested | No waveform at the live JTAG AXI boundary or physical response FIFO |
| Reset/clocks | Separate debug POR; coupled readiness-derived SoC/UI resets with local release synchronization; actual wrapper release exercised | No metastability simulation, physical timing signoff, or reset-during-outstanding proof here |
| Debug metrics | Handshake counters and freeze/snapshot semantics independently tested | Error counters check response status, not memory data integrity |
| Boot/result | Entry readback before final doorbell, run ID, done/result/flags/ready, retirement/trap/DDR error checks | `--full-reset-confirmed` is a user assertion, not a reset operation or hardware attestation |

Relevant source roots are `../software/`, `../rtl/` and
`../../ara_dsa_vcu118/rtl/{board,cheshire,axi,axi_llc,axi_riscv_atomics,common_cells}`.

## Actual Tests

1. 93 host loader, profile, integration and evidence-tool unit tests passed:
   `test_host_loader.py`, `test_profiles.py`, `test_host_integration.py`,
   `test_host_axi_netlist.py`, `test_host_axi_upload.py`, `test_host_burst_read_map.py`.
   Deliberate failing CLI messages in these tests are negative-test fixtures.
2. Nine exported probe/Tcl tests passed (`test_host_axi_probe.py`,
   `test_host_probes.py` in the exported software directory).
3. VCS debug register/observer simulation passed all 36 checks.
   Evidence: `/tmp/ara_host_debug_final_01`.
4. Integrated Verilator test now uses the actual `dram_wrapper_xilinx` and a
   separate approximately 300-MHz modeled UI clock against a 50-MHz SoC clock.
   Source SRAM remains generic and only the MIG AXI endpoint is modeled.
   Evidence: `/tmp/ara_host_chain_final_01`.

```text
PASS: host burst path checked_beats=2292 read_transactions=624 stalled_cycles=3388 cycles=35459
```

The integrated test covers single writes/burst reads, burst writes/single
reads, 1/2/3/16/256 beats, the board's +0/+8/+0x38/+0x40 offsets, cache-line
crossings, legal transactions on either side of a 4-KiB boundary, patterned
data and read backpressure. Other masters are idle. Compiler warnings are
retained in the evidence, not treated as a lint/DRC pass.

Archived gate tests are run by `check_host_llc_netlist.py`, using unmodified
Vivado functional exports and their included primitive models. This checks
cutter, AR/AW splitter, read-address logic, and write address/data/strobes.
It does not reconstruct optimized inter-module aliases or simulate memory.
Evidence: `/tmp/ara_llc_gates_final_01`. All five stages passed:

```text
ar_cutter: PASS cutter cases=122880
ar_splitter: PASS splitter cases=544 descriptors=1088
aw_splitter: PASS splitter cases=544 descriptors=1088
read_unit: PASS read_unit cases=72 requests=240
write_unit: PASS write_unit cases=72 requests=240
```

See its `result.json` for per-stage results and input/bench hashes. The write
test also checks varying data/strobes, W gaps, and SRAM/B backpressure. These
isolated tests check valid per-line descriptors with unlock granted; they do
not test complete cache coherence, all possible errors or descriptor contention.

## What the Board Pattern Does and Does Not Prove

Both captured regions were stable before/after the read-only diagnostic. The
returned words match independently read words at these offsets:

```text
start +0x00, LEN 3 -> +0x00, +0x48, +0x90
start +0x38, LEN 3 -> +0x38, +0x40, +0x88
```

For these observations, a data-match formula is
`(start & ~63) + 64*n + ((start + 8*n) & 63)`.
This is NOT a constant 72-byte stride and NOT a measured bus address formula.
It cannot by itself distinguish wrong addresses from wrong data selection.

- A DDR-only fault does not by itself explain SPM's same pattern, if the SPM
  request really takes the expected on-chip route.
- A Python-only decoding error does not explain the already-wrong raw DATA.
- Resetting the JTAG AXI core and refreshing DATA did not change the board result.
- Independent cell passes do not clear shared wiring, JTAG command handling,
  FPGA memory selection or physical behavior.
- Earlier `restored=true` verified the intended two scratch words only. The
  burst-write preflight may have changed an unintended location such as +0x48.
- `error_count=0` cannot detect an OKAY response carrying the wrong word.
- Outstanding counters track continuously, but cumulative metrics stop while
  frozen; a snapshot after software completion may not count a later probe.
- The 64-KiB blob run proved transfer/readback plus smoke completion, not CPU
  consumption of that blob, full-DDR testing or burst correctness.

## Remaining Falsifiable Alternatives

| Hypothesis | Distinguishing observation |
| --- | --- |
| Wrong JTAG command fields | At ARVALID && ARREADY, observe start, ARLEN=beats-1, ARSIZE=3, ARBURST=INCR; repeat for AW |
| Wrong shared interconnect/descriptor wiring | Compare accepted AR/AW fields at JTAG, post-atomics and LLC; compare each accepted descriptor and SRAM word address |
| Right address, wrong FPGA memory data selection | Correct SRAM/MIG requests but incorrect RDATA before the return interconnect |
| Return-side loss/duplication | Correct accepted R beats at LLC, different accepted beats at JTAG; inspect RVALID/RREADY/RLAST and response FIFO enables |
| Physical/reset fault | Correct functional netlist but failure depending on actual reset/clock/timing; requires physical reports/live samples, not functional export alone |

For `0x1401ff00`, LEN=2, size=3, the remapped LLC addresses should be
`0x1001ff00` and `0x1001ff08`, with word indices `0x7e0` and `0x7e1` in the
selected way. Check handshake cycles, not transient unaccepted bus values.

## One Remaining Transfer

Do not ask the Windows operator to repeat the already collected scratch tests.
The existing `host_axi_netlist.py --full --upload` command collects the exact
archived full functional netlist in one offline run, without synthesis,
implementation, programming or a board connection. It includes full logic and
memory initialization and uploads to an isolated evidence branch.

That file is required to inspect the omitted connections and JTAG logic on
Linux. If it still cannot distinguish the alternatives, explicitly report
that live boundary samples are missing instead of declaring a root cause or
promising that another static report will resolve it. Single-beat remains the
accepted operational route; no burst performance claim is justified.
