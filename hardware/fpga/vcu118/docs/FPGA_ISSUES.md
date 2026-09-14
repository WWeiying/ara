# FPGA Findings and Verification Boundary

## Evidence

The tracked Windows Vivado 2020.1 reports are under
`reports/synth_67f8334f3965/`. Synthesis finished on 2026-09-14.
The recorded input fingerprint is
`6AE175B608713C8C3182F15923147A010E223C67B4F29B870DA355696304F566`.
It matches the exported package before this constraint/diagnostic update.
It does not hash the generated XPR, IP output products, or DCP contents.
Synthesis completion is not timing, CDC, or board-level signoff.

## Blocking Findings

1. **QBS combinational feedback.** `drc.rpt` reports one LUTLP-1 violation
   involving eight LUTs. `check_timing.rpt` shows two overlapping feedback
   paths through compute/read logic and the weight/activation-needed outputs.
   These are netlist observations, not a proven RTL root cause. Static review
   shows `qbs_read_engine.fault_valid_o` depends on registered fault, burst-count,
   and stalled-address state. A direct combinational fault/needed feedback
   explanation therefore is not yet established. Do not insert arbitrary
   registers or set `ALLOW_COMBINATORIAL_LOOPS` based only on LUT names.

2. **Invalid DDR CDC exceptions.** The log reports unsupported `if`/`foreach`
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

Implemented in this update:

- Narrow, fail-closed FIFO CDC constraints and automatic existing-XPR file
  type migration. No IP configuration change or IP rebuild.
- `run.ps1 -Stage inspect` opens the recorded synthesis and writes separate
  reports using current constraints, even if RTL inputs are now stale.
  It never marks that synthesis as matching the updated sources.
- LUT INIT, per-pin net segments/drivers, top failing setup paths, clock,
  and ignored-exception reports. Inspection provenance accompanies reports.
- LUTLP-1 gates before implementation and after routing. No loop waivers.

Still pending actual Vivado verification:

1. Run `-Stage inspect` and confirm five `CDC:` summaries, nonempty clocks,
   and no large-through/missing-from/unsupported-control-flow diagnostics.
   Check `ignored_exceptions.rpt` and `clock_interaction.rpt` to verify the
   exceptions are active. Offline mocks do not prove real netlist matching.
2. Use `loop_cells.rpt` INIT values and drivers to reconstruct the eight-LUT
   feedback. Determine whether it is real request/ready feedback or another
   netlist mapping dependency. If RTL feedback is identified, expose the
   corresponding valid/ready, needed/complete, fault, and queue-state signals
   in one focused test before editing that path.
3. Rerun synthesis after a verified RTL change; then compare area and setup
   paths and perform routed timing/CDC/DRC checks. Do not equate a completed
   diagnostic run with a clean design.

No Vivado executable is available in the current Linux workspace, and the
Windows DCP is not present here. This update has not fixed or waived the QBS
loop, reduced the measured QBS area, or demonstrated timing closure.
