# FPGA Findings and Verification Boundary

## Current Status: Routed DDR Boundary Timing (2026-09-16)

The measured baseline is Windows Vivado 2020.1 `impl_1684ae5a235b`, uploaded
in `4d5a4b02`. It is fully routed, but setup/recovery fails: WNS -0.580 ns,
TNS -44.468 ns and 946 failing endpoints. Hold is now +0.009 ns and pulse/
skew is +0.039 ns, both with zero failing endpoints. The 50 MHz SoC group
has +0.892 ns setup slack. There are no no-clock or unconstrained internal
endpoints. This supersedes the pre-route hold/skew estimates below.

### Measured Causes and FPGA-Only Changes

- The worst recovery path runs from the last `i_ui_por` reset synchronizer
  to `fabric_ready_o_reg/CLR`. A reset test-bypass `tc_clk_mux2` maps to
  BUFGMUX/BUFGCTRL even though test mode is tied low. The path crosses SLR1
  to SLR2; 94% of its 2.979 ns delay is routing. The FPGA `rstgen_bypass`
  now uses ordinary reset/data muxes, allowing constant test mode to remove
  the bypass. Actual clock muxes are untouched. Asynchronous assertion,
  four-stage release and ASYNC_REG attributes are preserved. Recovery and
  removal are still timed; no internal reset false path was added.
- The 300 MHz FIFO write-data receiver has -0.176 ns on read-pointer decode
  through the 32:1 payload mux, with pointer fanout 4360. The reverse FIFO
  also has -0.134 ns on Gray-to-binary write-word/CE selection. Only local
  data selection changes: wide, 32-entry FIFOs use registered one-hot
  selection replicated per 64-bit slice. Read selection is a parallel
  masked reduction. Write word enables are local to each slice.
  Both advance on the same internal handshakes as the original pointers.
- This targets the separate 3 ns bundled-data violation (-0.168 ns) too.
  FIFO depth, payload bits, Gray pointer crossing, full/empty logic,
  synchronizer stages, spill registers and cycle latency do not change.
  Narrow FIFOs and other depths retain the generic implementation.
  The expected cost in the board's W/R FIFOs is 1216 selector FFs, protected
  from merging with DONT_TOUCH. Actual mapped area and routing must still
  be measured. An RTL rewrite alone does not prove timing closure.
- All five remaining Critical CDC findings in the routed baseline are
  internal to VIO, between its 50 MHz clock and the auto-selected 75 MHz
  debug hub clock. Debug constraints now connect the hub to the same
  free-running SoC net as VIO, with its frequency property set to 50 MHz.
  This uses the documented debug-port connection flow, not guessed
  generated clocks on hub outputs or a CDC waiver. Existing IPs are reused.
- Four asynchronous input pads now have a virtual zero-delay reference
  for IO/CDC coverage. First-stage-only 20 ns JTAG / 70 ns UART datapath
  bounds remain unchanged and override phase-based timing only on those
  paths. This bookkeeping reference does not make the pads synchronous.
  Later synchronizer stages retain normal timing.
- The reported DDR reset driver is UI-clocked `cal_RESET_n_reg[0]`.
  Its on-chip output propagation is bounded to one UI period (3.333 ns).
  This is a conservative design budget, not a DDR CK setup/hold claim;
  MIG still owns reset/CKE sequencing. LVCMOS12 is checked explicitly.
- The existing 3 ns FIFO pointer/data bounds are not relaxed. Explicit
  3 ns bus-skew constraints are added on each Gray-pointer crossing.

The two edited RTL files are only in the frozen FPGA package. Main RTL,
QBS/AKV, ASIC/DC and the three IP configurations are unchanged. The export
transform pins the reviewed FIFO source hash; an upstream protocol change
requires a new review. Do not refresh main RTL while validating this patch.

### Functional Evidence

`tests/check_cdc_fifo.py` compares the actual frozen FIFO with the unmodified
`4d5a4b02` FIFO. One bounded VCS run passes seven configurations, including
the real 582-bit W / 521-bit R payloads, both clock directions, 128/129-bit
slice boundaries and generic depth/width fallbacks. It compares ready,
valid, all output data, Gray pointers and the complete payload array every
cycle. Scoreboards check ordering; directed fill/drain and randomized stalls
cover full/empty, backpressure and pointer wrap. Four reset epochs include
full queues and stopped clocks. Per-slice one-hot state is checked against
the decoded binary pointer. Reset discards in-flight data in both versions;
independent one-sided warm reset is not supported or claimed.

`tests/check_jtag.py` also passes again with the new reset mux: 74 TAP scans,
45 accepted DMI requests per implementation, 20 phases, stopped TCK and
50 checks of the actual board/reset logic. Evidence and input hashes are in
`vcu118/results/20260916_cdc_fifo/` and `20260916_jtag_reset/`.
Full static elaboration has no non-vendor errors; VCS and static elaboration
are not metastability analysis or Vivado placement/routing validation.

### One Windows Validation Cycle

Run a new managed `-Stage synth`, then `-Stage impl` after synthesis succeeds.
Do not use `inspect` on the old netlist to validate these RTL changes.
The existing project and valid clkwiz/vio/ddr4 checkpoints remain in use.
No local Vivado is installed, so this patch has no new routed timing result.

Reports now include `bus_skew.rpt`, `methodology.rpt`, `io.rpt`,
`exceptions.rpt`, `hold_paths.rpt`, individual pad timing and
`boundary_checks.rpt`. Routed boundary checks reject reset BUFGs, missing
selector replicas, unconstrained/overridden or failing pad budgets, a
non-LVCMOS12 DDR reset, or different hub/VIO clocks.

Acceptance still requires WNS/WHS/WPWS >= 0, no bus-skew violations,
no new DRC/CDC Critical findings, and review of exception coverage and
unconstrained endpoints. The baseline's 1185 CDC-15 warnings are mainly
bundled FIFO data paths; inspect the real protocol and physical bounds,
not just the warning count. Bus-skew and methodology reports are additional
review evidence, not an automatic waiver or complete CDC signoff.

References: [AMD debug-core clocking](https://docs.amd.com/r/2024.1-English/ug908-vivado-programming-debugging/Debug-Cores-Clocking-Guidelines),
[asynchronous constraints](https://docs.amd.com/r/2021.2-English/ug903-vivado-using-constraints/Constraining-Asynchronous-Signals),
[DDR4 pin rules](https://docs.amd.com/r/en-US/pg150-ultrascale-memory-ip/DDR4-Pin-Rules).

## Previous Update: Sampled JTAG and Registered Reset CDC (2026-09-15)

This change includes the dispatcher patch below and modifies only the frozen
FPGA package, its export transforms, constraints and tests. It does not refresh
main RTL, change QBS/AKV, alter the three IP configurations, or update ASIC/DC.
The latest actual Vivado evidence is still `synth_f18665bfb9ae`, not this patch.

### Root Cause and Changes

- The baseline's 800 JTAG/SoC Critical CDC findings come from the TAP-clocked
  DMI request/response and reset-phase handshakes. J53 TCK (P30) also drives an
  inverted-clock DFT BUFGMUX, causing PLCK-58 on a non-clock-capable input.
- The FPGA copy retains the original TAP state machine and shift registers,
  but clocks them with the SoC clock. Three-stage ASYNC_REG chains sample TCK,
  TMS and TDI. Rising/falling TCK edge enables replace the external clock and
  DFT clock mux. DMI now shares the DM clock; the old clearable CDC source is
  retained for other users but is not instantiated by this TAP.
- Requests hold valid/data through backpressure and responses complete even
  with TCK stopped. TAP reset/DTM hard reset cancels unaccepted requests and
  synchronously flushes the DM response FIFO. Already accepted writes are not
  undone. Both handshakes are isolated during clear and the flush cycle.
- The four baseline CDC-10 paths included combinational reset/ready logic
  before synchronizers. VIO reset is now registered in its own SoC domain;
  external reset/clock loss still asserts it asynchronously. DDR ready is
  registered in the UI domain, after a separate reset-release synchronizer,
  before crossing to the SoC reset/status chains. Both AXI FIFO sides reset
  together, including when the UI clock stops. Reset chains carry ASYNC_REG.
- No sampled-TAP `create_clock`, asynchronous clock group or
  CLOCK_DEDICATED_ROUTE waiver remains. Only each input's first-stage D pin
  gets a 20 ns pad budget; TDO gets a 20 ns output datapath budget. Later
  stages and TAP/DMI paths use normal SoC timing. Existing DDR bounds remain.
  Legacy `inspect` reconstructs the old JTAG timing explicitly and warns that
  it cannot validate the new clocking/reset architecture.

### Required External JTAG Contract

Use **TCK <=1 MHz**, high and low phases each **>=400 ns**, and change TMS/TDI
on falling TCK. The SoC clock must be **>=50 MHz**, running and out of reset.
This intentionally replaces the earlier 10 MHz external-TCK configuration;
it is not a drop-in 10 MHz implementation. J53 wiring and DMI commands do not
change. FPGA USB-JTAG/VIO is separate and unaffected. CPU TAP access before
DDR calibration/SoC reset release is not available; use VIO for that diagnosis.

Set `adapter speed 1000` in the external OpenOCD configuration before `init`
and remove any reset-event override that raises it. This command uses kHz;
see [OpenOCD adapter configuration](https://www.openocd.org/doc/html/Debug-Adapter-Configuration.html).
Clock-enable use follows [AMD UG949](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Using-Gated-Clocks);
the particular sampled-TAP timing contract is our design requirement, not an
AMD claim or hardware qualification.

### Evidence and Acceptance

`tests/check_jtag.py` compares the patched TAP against the pinned `74042fbd`
TAP/DMI CDC with a ready/valid DM response-queue model. VCS passes 74 checked
scans and 45 accepted requests per implementation, all 16 TAP states, 20
clock phases, both 40/60% duty cycles, IR/DR pause, BUSY/failed status,
soft/hard reset, queued-response flush, stopped TCK, SoC reset and TRST.
The same bounded run extracts the actual board/DDR reset logic and passes 50
reset checks including calibration loss, VIO reset and stopped UI clock.
Results and source hashes are under `vcu118/results/20260915_jtag/`.
The constraint-query test passes 27 cases, including missing/wrong stages,
missing pads, too-slow SoC clock and legacy inspection. Full static package
elaboration has no non-vendor errors; vendor cells/IP require Vivado.

These are digital functional/static checks, not metastability simulation,
routed CDC/DRC signoff, or an actual debugger/board test. Re-run **synth**, not
`inspect`, using the existing project/IPs. In the new netlist verify no JTAG
clock/DFT mux/DMI CDC instance, all nine sampling FFs preserved, no old four
CDC-10 structures, and no PLCK-58. Then inspect route timing, CDC, reset
recovery/removal and physical IO budgets. The earlier dispatcher timing,
DDR hold/pulse and debug-hub/no-clock issues still need new Vivado evidence;
this patch does not claim all FPGA violations are cleared.

## Dispatcher-Only Timing Patch (2026-09-15)

The frozen Windows baseline is `synth_f18665bfb9ae`, input fingerprint
`B229D9E90114A9DDA31D23172E9F3CABD470DEA3BC656D5D8853E63C1C19C0F4`.
It contains 650867 LUTs (QBS: 113982), 235830 FFs, 433 RAMB36,
17 RAMB18, eight URAMs and 257 DSPs. Compared with `synth_1357d6f785ab`,
total LUTs fell 12.8% and QBS LUTs fell 45.0%. QBS is now 17.5% of total
LUTs. There are no LUTLP-1 loops; REQP-1851 is no longer reported.

Setup still fails: WNS -1.283 ns, TNS -189.161 ns, 224 endpoints. All 50
reported worst setup paths run from dispatcher
`overlap_elements_per_reg_q_reg[0]` to `eew_q_reg[*][*]/CE`.
The worst path has 84 logic levels, including 22 CARRY8s, and 20.994 ns
estimated data delay. The named nets trace active-element calculation,
64-bit slide bounds, register-interval calculation, layout/ready decisions,
segment request selection and the final EEW write enable.

### Targeted Change and Evidence

Only the exported FPGA dispatcher and segment sequencer change in this portion. Main
`hardware/src`, DC scripts, QBS/AKV datapaths, board wiring, clocks, CDC
constraints, reset protocols and IP configurations are unchanged by this patch.
This is NOT a refresh from the concurrently changing main RTL.

- Slide bounds now carry only through the VL-sized low word (11 bits for
  VLEN=1024); upper-stride reduction checks preserve the original modulo-2^64
  overflow, scalar decrement, borrow and capacity clamp.
- Active register coverage is an eight-bit parallel interval mask. Reshuffle
  checks and EEW writes consume the mask directly, eliminating the late
  first-register/count/index-add chain. Count users get a balanced reduction.
- Architectural decoding and maintenance micro-ops now build separate request
  candidates. A current-state mux selects the backend request. Maintenance
  interval arithmetic no longer supplies the architectural layout helpers;
  the original token, idle payload, and blocked-decode behavior are retained.
- A segment-sequencer sideband computes EEW destination geometry before the
  late request-valid/ready decision. Only actual EEW-writing handshakes consume
  it. This separates first-segment interval calculation from transfer approval
  without changing the real request payload, segment state, or latency.
- No register, cycle, ready/valid condition, reset or EEW update guard is added
  or removed. Unsupported EW fallback behavior is also preserved.
- `vcu118/dispatcher_fpga.py` and `dispatcher_control_fpga.py` reapply these
  paired transforms during export. The control transform pins the reviewed
  source hashes and rejects changed upstream versions rather than silently
  combining them with the FPGA patch. Opt-in uop traces follow the selected
  backend request, including maintenance operations.

The focused VCS comparison passes 2364768 arithmetic/layout vectors across
VLEN=64/1024/65536, including LMUL/EW encodings, v31 clipping, empty/reversed
intervals, 64-bit wrap and scalar borrow. A boundary test first exposed the
old two-state integer fallback for unsupported EW; the patch preserves it.
The dispatcher comparison passes 68640 cycles, comparing outputs and 70
registered state signals, with 13542 blocked and 25379 accepted requests.
State-cofactor injection exercises all 15 defined states; it is not a claim
that random instruction traffic naturally reaches every overlap state.
The old dispatcher uses its own unmodified segment sequencer in this test.
There are 1280 additional nonzero repair/segment-phase combinations, with
backpressure and boundary intervals. Another 64 held legal segment loads
exercise field zero, including nonzero vstart. The geometry assertion runs
13685 times on EEW-writing handshakes (128 first-segment and 13318 later-segment
observations). The first-segment coverage check initially found a hole in the
random traffic; the directed loads close it. No RTL behavior was relaxed to
pass that check. All original overlap-context assertions remain enabled.
This is differential simulation, not formal equivalence or FPGA timing proof.
One local standard-cell DC comparison was attempted in a separate directory.
The baseline hit its 300-second bound while analyzing the standard-cell
libraries, before mapped timing was available; the candidate run was not
started. This attempt supplies no area/timing improvement measurement and was
not retried with different RTL or synthesis settings.

Reproduce with one bounded check (VCS required, reference commit retained):

```sh
python3 hardware/fpga/vcu118/tests/check_dispatcher_layout.py /tmp/fpga_dispatcher_check --vcs /path/to/vcs
```

Current evidence is in repository
`hardware/fpga/vcu118/results/20260915_dispatcher_control/`; the earlier
arithmetic-only evidence remains in `results/20260915_dispatcher/`.
No Vivado installation is available locally, so no new synthesis, placement or routing
result is claimed. Run one new managed `-Stage synth`, retaining the three
existing valid IP checkpoints. Compare setup paths, utilization and loops with
the baseline above. Do not use old-netlist `inspect` to validate this RTL.

In the new `setup_paths.rpt`, check whether repair context still traverses
architectural slide/layout logic, whether segment valid still precedes interval
arithmetic, and where the new worst path moves. Review all 224 old endpoints,
not just the top path. Do not change clocks, add false paths, or claim closure
from the source rewrite. This follows the RTL-path-first approach in
[AMD's timing-closure guide](https://docs.amd.com/r/2022.1-English/ug949-vivado-design-methodology/Timing-Closure).

### Remaining Items, Not Waived

- 804 CDC Critical findings remain in the baseline. 800 are on the external
  JTAG/SoC crossing; the six reset-aware bundled-data handshakes now have
  active bounds (18 exceptions, 100% through coverage). Structural findings
  still require protocol/reset review; bounds alone do not prove CDC safety.
  Four reset/status findings also remain. No waivers were added.
- PLCK-58 remains on the external RISC-V JTAG clock route from the existing
  non-clock-capable board pin. The redundant BUFG fix does not make this a
  dedicated clock route. Board routing or a separately verified TAP clocking
  change is still required; no fake clock or timing exclusion was added.
- The 533 no-clock pins are driven by the debug hub's pre-implementation
  outputs. `clock_io.rpt` confirms `IS_BLACKBOX=1` and a real 75 MHz input
  clock. Recheck after debug-core insertion in implementation; do not define
  guessed clocks on its outputs or treat pre-route placeholders as signoff.
- Hold (-0.154 ns) and DDR pulse-width (-0.029 ns) are synthesis estimates.
  UART input-delay coverage and DDR reset output constraints still need
  interface review. Routed timing, unconstrained endpoints, CDC and DRC must
  be reviewed before hardware use.

## Previous Update: Control RTL and DMI Constraints (2026-09-15)

This section supersedes the historical findings below. The latest measured
Windows result is `synth_1357d6f785ab`, input fingerprint
`542A5114A34855C5BF71FA95C950AE89E82174D6A4F3EC4C45FCE5AA9E3938BC`.
It completed synthesis: 746409 total LUTs, 207332 QBS LUTs, zero LUTLP-1
violations. Setup still has WNS -0.743 ns, TNS -68.600 ns and 210 failing
endpoints. This result does NOT include the following refresh.

### Refreshed RTL

The snapshot now includes the six modified source modules: dispatcher, VMFPU,
QBS engine, compute engine, block adapter and profile decoder. In particular,
dispatcher decode uses current-state conditions instead of the complete
next-state expression. The existing verification record at
`verification/timing/results/20260915_control_timing/summary.json` matches the
current upstream source hashes. It records the 67040-cycle dispatcher comparison,
12 SoC regressions, 33 QBS commands and six real-data slices. This is reused
functional evidence, not formal equivalence or a new FPGA timing result.

### DMI CDC Correction

The latest CDC report has 804 Critical findings, 800 between external JTAG and
the SoC. Many are fanout from the reset controller's bundled phase word; they
are not 800 independent missing synchronizers. `cdc_2phase_clearable` explicitly
requires `max_delay = min(source_period, destination_period)` on req/ack/data.
Its reset controller uses two non-decoupled four-phase handshakes to isolate,
clear and release both domains, including when one side resets alone.

The blanket JTAG asynchronous clock group has been removed: it would override
these physical bounds. `cdc.xdc` now constrains all six handshakes (two DMI
channels plus four reset-phase directions), using 18 bounded exceptions through
only their async output ports. Source and destination are clocks, avoiding
segmentation at hierarchical pins. The current bound is 20 ns in both
directions, derived from actual clocks. Normal inter-stage timing is retained.
The req/ack synchronizer stages are checked and marked ASYNC_REG; data and state
registers are not marked as synchronizers. Missing ports, changed data widths,
missing clocks, or changed stages are errors rather than silently empty rules.

No handshake RTL, reset latency, data qualification, or CDC waivers were changed.
These timing bounds do not by themselves prove bundled-data correctness or
eliminate structural CDC-1/4 findings. In the next reports verify DMI paths use
Max Delay Datapath Only, not Asynch Clock Groups, and inspect both
`ignored_exceptions.rpt` and the new `exception_coverage.rpt` for overrides or
empty paths. The offline query tests are not an actual Vivado netlist check.

### Clock and I/O Corrections and Open Items

- The top-level JTAG port now carries RTL `CLOCK_BUFFER_TYPE="NONE"`. The TAP
  already instantiates a BUFGMUX. The latest DRC found an additional inferred
  BUFG feeding that mux (REQP-1851); setting the attribute at RTL input inference
  is intended to remove that extra buffer. The retained non-dedicated-route
  exception is for the existing board pin, not a timing waiver. Re-synthesis
  must verify the actual buffer chain and placement legality.
- UART RX already uses `UART_IS_SIN` with two FFs. Mark those ASYNC_REG and
  apply the existing 70 ns physical budget only from the RX pad to the first
  D pin, using datapath-only timing. Do not invent a synchronous UART launch
  phase; the second stage remains normally timed. `check_timing` can still flag
  a lack of conventional input delay on this asynchronous interface.
- 533 missing-clock pins in the current report originate at debug-hub outputs
  `sl_iport0_o[1]` and `sl_iport1_o[1]`. The new `clock_io.rpt` records hub
  black-box status, actual clocks, and net drivers. Determine whether these are
  pre-implementation debug-core placeholders before changing clock definitions.
  Do not create arbitrary clocks on the hub outputs or confuse FPGA debug-hub
  JTAG with the separate external RISC-V DMI JTAG port.
- DDR reset output `c0_ddr4_reset_n` remains an open interface-constraint review.
  Its driver is included in `clock_io.rpt`. No invented output delay or blanket
  reset-output exception has been added. MIG reset sequencing and pulse widths
  require separate verification; an output-delay declaration cannot prove them.
- The other four CDC Criticals involve composed reset/ready signals into status
  or reset synchronizers. They remain visible: no changes to functional POR,
  calibration gating, or reset release were made without waveform evidence.

The same managed synth/inspect/impl flows generate the added reports. Existing
valid clkwiz/vio/ddr4 checkpoints are reused; no IP parameters changed. Run one
new synthesis of the frozen package, review the constraints and critical paths,
then perform implementation. An old-netlist `inspect` cannot validate the new
dispatcher or JTAG buffer attribute. No local Vivado run or routed signoff has
been performed for this update.

References: [Clock exception priority](https://docs.amd.com/r/2021.1-English/ug1387-acap-hardware-ip-platform-dev-methodology/Clock-Exceptions-Precedence-Over-set_max_delay),
[CLOCK_BUFFER_TYPE](https://docs.amd.com/r/2023.1-English/ug912-vivado-properties/CLOCK_BUFFER_TYPE),
[Exception coverage](https://docs.amd.com/r/2020.2-English/ug906-vivado-design-analysis/Reporting-the-Timing-Exceptions-Coverage).

## Historical Investigation

## Evidence

The tracked Windows Vivado 2020.1 reports are under
`reports/synth_67f8334f3965/`. Synthesis finished on 2026-09-14.
The recorded input fingerprint is
`6AE175B608713C8C3182F15923147A010E223C67B4F29B870DA355696304F566`.
It matches the exported package before this constraint/diagnostic update.
It does not hash the generated XPR, IP output products, or DCP contents.
Synthesis completion is not timing, CDC, or board-level signoff.

The follow-up `reports/inspect_a1c3e095ccee/`, uploaded in commit `98bbc6ea`,
opens that SAME synthesis with updated constraints. `inspection.json` records
the old fingerprint and current input fingerprint
`F308DBE04C3815ADB1831A21F30A06F7840713C002367E509BA1A19044C6AE57`.
This is not a synthesis of the subsequent board RTL changes below.

## Follow-up Inspection

- The new FIFO max-delay exceptions are active in both directions:
  `cdc.rpt` identifies pointer and spill-data paths as Max Delay Datapath Only.
  `clock_interaction.rpt` shows the 3 ns requirement. `ignored_exceptions.rpt`
  contains only three non-existent MIG-internal reset false paths, not the
  added FIFO constraints. This establishes exception application, not complete
  CDC signoff or routed timing closure.
- DDR-to-SoC still has an unsafe clock-pair classification. A concrete path is
  DDR `div_clk_rst_r1_reg` through `fabric_ready` to VIO
  `probe_in_reg_reg[2]/D`, sampled at 50 MHz without a synchronizer. The board
  update now samples each of the four independent VIO status bits through the
  existing two-stage `sync` module. These are debug indicators, not an atomic
  status word or a functional handshake. Only first-stage D pins are excepted;
  subsequent stages remain timed. Sampling continues while SoC reset is held,
  as long as `soc_clk` runs. The VIO IP and functional reset paths are unchanged.
- The eight-LUT QBS loop remains. LUT INIT and pin connections establish both
  `compute_fault -> activation_needed -> read selection -> compute_fault` and
  the corresponding weight-needed cycle in this netlist. `compute_fault` is
  driven by `i_compute_engine_i_2`, whose I1 comes from `i_compute_engine_i_166`;
  that LUT consumes `phase_compute_o`, read `busy_o`, and `i_read_engine_i_224`.
  However, the current RTL's compute fault uses only registered engine state
  and `qbs_read_engine.fault_valid_o`, itself derived only from registers.
  A synthesis mapping/shared-decode dependency or a historical input mismatch
  are hypotheses, not established causes. The non-loop side inputs of these
  LUTs were absent from the first diagnostic dump. New `loop_fanin.rpt` walks
  these inputs up to sequential boundaries, with a 2048-cell cap and explicit
  truncation. Do not remove fault gating or alter QBS latency on this evidence.
- Setup WNS remains -0.743 ns, TNS -68.600 ns, with 210 failing endpoints.
  Area and QBS logic are unchanged because this inspection uses the old DCP.

## Blocking Findings

### Targeted Fault-Decode Correction

The extended `inspect_9a3426f975cc` dump reaches its 2048-cell bound with 1595
cells pending, but contains all nine LUTs needed to evaluate the fault side of
the feedback edge. Exhaustive evaluation of four engine state bits, four phase
signals, read busy, and read fault (1024 independent boundary combinations)
shows that changing `i_read_engine_i_224/O` never changes `compute_fault`.
It changes the inner `i_compute_engine_i_166/O` in eight combinations, but the
outer state qualification masks those changes. This proves the edge redundant
in the captured two-state steady Boolean function; it does not prove absence
of physical races, complete netlist equivalence, or a specific Vivado bug.

The FPGA export now implements the original fault expression with one
`DONT_TOUCH` LUT5, driven only by `state_q[3:0]` and `read_fault_valid`.
INIT is derived from the named enum constants (currently `32'h00600040`).
The export rejects changed state encodings or a changed fault expression for
review. No fault register, added cycle, removed gating, or loop waiver is used.
ASIC/source RTL retains the original expression. The focused VCS check covers
all 32 binary input combinations using the actual exported decoder and the
original expression; the primitive model is a truth table, not Xilinx timing.

The same update synchronizes the existing QBS ingress changes. The 95 source
hashes in `verification/timing/results/20260914_ingress/summary.json` matched
the upstream files at synchronization. Existing evidence includes 33 QBS
commands, seven real-data slices, SRAM functional checks and representative
RVV checks. This evidence is reused, not counted as a newly run FPGA test.
There is no measured FPGA area or timing improvement for this new package yet.

Run one new `-Stage synth`, reusing the existing three IP checkpoints. It already
generates timing, utilization, CDC and loop reports, and now always adds the
bounded `fault_decode.rpt`, even when no loop remains. Confirm the preserved
`i_fpga_compute_fault` LUT and register-bounded inputs there, and zero LUTLP-1
violations in `loops.rpt`. Old inspection netlists have no such cell and produce
an empty fault-cone report. Do not repeat inspection of the old netlist to
validate this RTL update. Route only after reviewing the new synthesis reports.

Reproduce the short offline check with:

```sh
python3 hardware/fpga/vcu118/tests/check_qbs_fault.py /tmp/qbs_fault_check --vcs /path/to/vcs
```

Primitive and preservation semantics: [LUT5](https://docs.amd.com/r/en-US/ug974-vivado-ultrascale-libraries/LUT5),
[DONT_TOUCH](https://docs.amd.com/r/en-US/ug912-vivado-properties/DONT_TOUCH).

### Remaining Signoff Checks

1. **QBS combinational feedback.** `drc.rpt` reports one LUTLP-1 violation
   involving eight LUTs. `check_timing.rpt` shows two overlapping feedback
   paths through compute/read logic and the weight/activation-needed outputs.
   These are netlist observations, not a proven RTL root cause. Static review
   shows `qbs_read_engine.fault_valid_o` depends on registered fault, burst-count,
   and stalled-address state. A direct combinational fault/needed feedback
   explanation therefore is not yet established. Do not insert arbitrary
   registers or set `ALLOW_COMBINATORIAL_LOOPS` based only on LUT names.

2. **Original invalid DDR CDC exceptions, application now verified.** The original log reports unsupported `if`/`foreach`
   in managed XDC, a 166128-pin `-through` collection, and a rejected
   `set_max_delay -datapath_only` without `-from`. The updated flow loads this
   file as unmanaged Tcl, after IP clock constraints. It bounds both Gray
   pointer directions and the destination data capture of each of the five
   AXI FIFO channels to 3 ns, with nonempty endpoint/clock checks. Ordinary
   timing between synchronizer stages is retained. Existing synchronizers
   already carry ASYNC_REG in RTL; this is not a claim that they were absent.

3. **Timing is not closed.** The synthesis report shows setup WNS -0.743 ns,
   TNS -68.600 ns, and 210 failing endpoints at the 50 MHz SoC target.
   Its worst reported setup path is in the Ara dispatcher, from
   `overlap_elements_per_reg_q_reg[0]` to `eew_q_reg[11][0]/CE`, with 83 logic
   levels and 20.454 ns data delay. The hold result is pre-placement and must
   be reevaluated after valid CDC exceptions and routing. Do not waive hold
   checks or claim closure from a synthesis-only report.

4. **Other CDC/clock findings need review.** The original report has 806
   critical CDC findings (798 CDC-1, 5 CDC-4, 3 CDC-10). These are findings to
   classify, not 806 established functional bugs. Review the VIO observation
   of DDR `fabric_ready`, reset crossings, debug-hub clocking, and unconstrained
   ports separately. The FIFO constraint correction does not resolve these
   by itself and adds no blanket CDC waivers.

## QBS Area

`utilization.rpt` attributes 365997 LUTs to QBS, of which 361309 are under
the compute engine. The following breakdown avoids double-counting parents:

| QBS component | LUTs | Share of QBS LUTs |
| --- | ---: | ---: |
| Two payload buffers, including their memories | 208109 | 56.9% |
| Two adapters, excluding the payload buffers | 105856 | 28.9% |
| Decoder | 24613 | 6.7% |
| Dot unit | 3699 | 1.0% |
| Remaining logic | 23720 | 6.5% |

The payload data selector in `qbs_payload_buffer.sv` implements a 16-way
last-matching-byte priority selection. Its use across rows, planes, slots,
and metadata creates 1216 byte selectors per buffer. This is a concrete
candidate for reducing duplicated selection/decode logic, not a measured
optimization yet. The two buffers also use 192 RAMB36 primitives for only
3584 logical payload bytes in shallow, wide memories. Any LUTRAM/BRAM change
must preserve byte enables, read latency, and read/write collision semantics.
Neither changing memory attributes nor reducing supported formats is an
accepted fix without resource measurements and functional regression.

## Implemented and Pending

Implemented across these updates:

- Narrow, fail-closed FIFO CDC constraints and automatic existing-XPR file
  type migration. No IP configuration change or IP rebuild.
- `run.ps1 -Stage inspect` opens the recorded synthesis and writes separate
  reports using current constraints, even if RTL inputs are now stale.
  It never marks that synthesis as matching the updated sources.
- LUT INIT, per-pin net segments/drivers, top failing setup paths, clock,
  and ignored-exception reports. Inspection provenance accompanies reports.
- Bounded loop fanin including supporting LUTs and sequential boundaries.
- Independent two-stage VIO status sampling, with narrow first-stage exceptions.
  Only inspection may open a legacy netlist missing these synchronizers; it
  emits a warning and cannot verify the RTL fix. New synthesis/implementation
  requires all eight status registers and four first-stage D pins to match.
- LUTLP-1 gates before implementation and after routing. No loop waivers.

Still pending actual Vivado verification:

1. After re-synthesis, verify the four VIO synchronizer chains in `cdc.rpt`,
   their first-stage-only exceptions, and the DDR-to-SoC clock interaction.
   The VCS test checks wiring/latency under 40 transitions, not metastability
   or placement. Existing 806 critical CDC findings still require classification.
2. The extended old-netlist inspection and fault-side Boolean check are now
   complete. Validate the dedicated FPGA fault LUT in one new synthesis,
   using its automatically generated `fault_decode.rpt` and `loops.rpt`.
   The mapping correction has not yet been verified in Vivado.
3. Rerun synthesis after a verified RTL change; then compare area and setup
   paths and perform routed timing/CDC/DRC checks. Do not equate a completed
   diagnostic run with a clean design.

No Vivado executable is available in the current Linux workspace, and the
Windows DCP is not present here. This update has not fixed or waived the QBS
loop, reduced the measured QBS area, or demonstrated timing closure.

## Windows Synthesis Crash (2026-09-14)

The user-provided log excerpts for `synth_1e29d62d80ed` show a new synthesis
attempt, not an inspection of the earlier netlist. The run reached
`Start Timing Optimization`, then printed:

```text
An unrecoverable error has occurred, synthesis cancelled.
TclStackFree: incorrect freePtr. Call out of sequence?
```

The directory listing contained only `.vivado.begin.rst`, with no top-level
DCP or end/error marker. The outer monitor continued printing
`Running synth_design` until 2026-09-15 04:34. This is not a successful new
synthesis or an area/timing result. The reported memory peak alone does not
establish out-of-memory as the cause; preserve the full run/session/crash
logs before changing RTL, tool versions, or synthesis options.

The monitor now checks the last 64 KiB of `runme.log` on each poll for these
explicit fatal diagnostics, even when Vivado leaves STATUS stale. It does
not impose a quiet-log timeout, kill processes, or reset existing IP runs.
Offline tests cover log-only crashes, delayed diagnostics, CRLF and EOF
handling, and nonfatal/echoed text. This fixes missed crash detection, not
the underlying Vivado crash; Windows/Vivado verification remains pending.


The full logs are now tracked under `reports/failed_synth_1e29d62d80ed/`
(commit `bab087e1`). They confirm:

- All three IP runs (`clkwiz`, `vio`, `ddr4`) were reused; licensing succeeded.
- Synthesis used the default directive with `-flatten_hierarchy none` and
  reported a maximum of four helper processes.
- Cumulative elapsed times were 00:14:33 at RTL elaboration, 01:24:36 at
  cross-boundary/area optimization, and 01:26:23 after applying timing XDC.
- There is no earlier `ERROR:` or `CRITICAL WARNING:` diagnostic and no
  explicit allocation failure in either uploaded log. Synthesis did not parse
  `cdc.xdc`; the earlier oversized CDC collections are not reported here.
- Three `simd_mul` rounding-variable latch warnings remain a separate review
  item. Neither those warnings nor the 19600 MB peak identifies the crash cause.

The monitor patch was also checked directly against the uploaded log: it
rejects this run without consulting Vivado STATUS or requiring an error marker.
The logs have no internal crash stack. Collect any existing `hs_err_pid*.log`
or `vivado_pid*.str` before another synthesis; their absence is not evidence
of a successful run. Do not claim that the monitor patch repairs synthesis.

## QBS RTL Refresh (2026-09-15)

The next FPGA snapshot includes the verified shared byte-alignment path in
`qbs_block_adapter` and `qbs_payload_buffer`. Production adapters enable
`StreamWriteData`; standalone arbitrary-target payload clients keep the
generic selection path by default. The change preserves write masks, slot
priority, SRAM capacity and pipeline depth. It targets duplicated byte-data
selectors, not the Vivado timing-optimization crash.

Repository evidence is under
`verification/timing/results/20260914_qbs_stream_area/`. Before export, the
collector rechecked current RTL hashes and completed test records: 33 commands
and seven real-data slices retain identical engine cycles; adapter, macro,
generic-payload and RVV/AKV handoff checks also passed. This is reuse and
verification of existing simulation evidence, not a new FPGA synthesis.

Run `scripts/run.ps1 -Stage synth`, not `inspect`, to measure the refreshed
RTL. The managed flow uses a fresh top-level run directory and reuses the
three completed, non-stale IP runs. Do not reset/recreate the project or IPs.
No new Vivado area, loop, CDC or timing result is available for this snapshot.
