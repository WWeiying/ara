# FPGA Findings and Verification Boundary

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
2. First run `-Stage inspect` again to collect `loop_fanin.rpt` from the old
   synthesis without rebuilding IP. Use its LUT INIT values and drivers to
   distinguish real RTL feedback from another mapping dependency or mismatched
   historical inputs. If RTL feedback is identified, expose the
   corresponding valid/ready, needed/complete, fault, and queue-state signals
   in one focused test before editing that path.
3. Rerun synthesis after a verified RTL change; then compare area and setup
   paths and perform routed timing/CDC/DRC checks. Do not equate a completed
   diagnostic run with a clean design.

No Vivado executable is available in the current Linux workspace, and the
Windows DCP is not present here. This update has not fixed or waived the QBS
loop, reduced the measured QBS area, or demonstrated timing closure.
