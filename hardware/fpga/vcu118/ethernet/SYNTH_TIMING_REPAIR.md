# Combined synthesis timing repair

Latest full-path review and fixed-ID protection candidate:
[TIMING_INVENTORY_20260927.md](TIMING_INVENTORY_20260927.md).
It enumerates all 636 setup endpoints and all failing clock-pair categories;
the paired local improvement is not yet full-design acceptance.

## Acceptance policy

Update, 2026-09-27: the user now permits the specifically identified vendor
PHY hold and MIG PLL_CLK/RIU_CLK MaxSkew violations to remain at synthesis,
subject to integration/previous-change review before proceeding. This
supersedes the earlier requirement to resolve those two checks before a new
full synthesis. It does NOT waive arbitrary hold failures, setup, actual
pulse-width failures, missing clocks, CDC correctness or routed timing.
See `TIMING_REAUDIT_20260927.md` for the current review and its limits.

The next run is synthesis-only. The existing all-negative-slack gate remains
conservative; its failure preserves reports/DCP for path-level review rather
than auto-starting implementation. Do not treat that failure alone as a new
RTL regression, or change the summary's global WHS/WPWS threshold to waive
unrelated paths. Implementation requires checking the complete new violation
set against the two authorized categories. Routed timing has no such waiver.

### Earlier policy and stopped runs

The user explicitly requires **all synthesis timing checks to pass before any
implementation**. This includes setup, hold and pulse-width/skew checks. Keep
the managed-run gate in `scripts/run_support.tcl`; do not bypass it, add broad
false paths, invent clock latency, reduce jitter, or alter report parsing to
make an unplaced design appear accepted. No placement, routing, bitstream or
board operation is authorized while this gate fails.

Before any NEW full-design synthesis, the user additionally requires PHY hold
and MIG skew to be resolved, followed by a separate review checkpoint. A local
tool run completing is not sufficient authorization to advance. Record:

- Root-cause evidence and why each change addresses it without masking checks.
- Review of clock definitions, generated clocks, exceptions and CDC/reset paths.
- Relevant local setup, hold and pulse-width/skew results, including coverage
  limits, missing paths and any unresolved warnings.
- Focused functional regressions and consistency of source/exported RTL,
  configuration and the tested source hashes.
- An explicit review conclusion with no unresolved blocking findings.

Only after this review passes may a new immutable full-design synthesis start.
Missing evidence or unresolved issues keep global work stopped. This review
does not replace the subsequent full-design synthesis timing gate or authorize
implementation, bitstream generation or board programming on its own.

The previous frozen run `ara_combined_20260927_0320` remains stopped. Do not
edit or restart its snapshot. Its report is
`package/reports/synth_dad02fcce478/timing_summary.rpt`:

| Check | Worst slack (ns) | Failing endpoints |
| --- | ---: | ---: |
| Setup | -1.050 | 772 |
| Hold | -0.413 | 137284 |
| Pulse-width/skew | -0.029 | 16 |

## Root-cause separation

Setup: all setup failures in that summary are in the 300-MHz MIG UI domain.
The first 50 failing paths lead through the shared DDR mux and the dynamic AXI
ID remap table. The worst write path has 20 logic levels and 4.802 ns estimated
data delay. In the table, variable-index read/modify/write creates selected
counter muxes, arithmetic and writeback demuxes after ID lookup/full detection.

Hypothesis: per-entry counter arithmetic with decoded enables removes those
selected-counter muxes without changing latency, capacity or ordering. The
distinguishing simulation signals are `table_q`, `table_d`, push/pop entry IDs,
input IDs, free bits, lookup/full outputs and returned IDs; compare every cycle,
including simultaneous push/pop. Physical evidence must show the old
selected-counter path disappearing or shortening under unchanged constraints.

The FPGA export now transforms only this table update via
`axi_remap_fpga.patch_axi_remap`. It retains the existing library's ID lookup,
allocation FSM, all interface signals and all configuration limits. Per-entry
increment/decrement cancels on same-entry push/pop; the input ID still updates
on push, including that simultaneous case. No upstream dependency is modified.

Hold is separate: the -0.413-ns path is a zero-logic-level FDRE-to-TX_BITSLICE
path **inside the vendor Ethernet PCS/PMA**, with unplaced clock and net delay
estimates. It is not the ID table, nor an asynchronous crossing that can simply
be excluded. Numerous other hold failures occur in existing SoC/loader domains.

The -0.029-ns entry is specifically **Max Skew** between MIG
`BITSLICE_CONTROL/PLL_CLK` and `RIU_CLK`, reported in the pulse-width section.
The displayed actual min period and high/low pulse-width checks are positive
(+0.042 ns and +0.039 ns respectively). Do not misdiagnose this as a too-short
DDR pulse or change DDR frequency on that basis.

These unplaced physical checks are still blockers under the user's policy.
No fix of the AXI setup cone proves them resolved. AMD describes hold fixing
and final verification as part of the physical flow:
[UG949, Pre and Post-Route](https://docs.amd.com/r/2020.2-English/ug949-vivado-design-methodology/Pre-and-Post-Route).
That methodology is not permission to override the chosen gate.

## Validation

- `test_axi_remap_patch.py`: three export-context/roundtrip tests pass.
- `test_export.py`: 33 existing export regression tests pass.
- `check_axi_remap.py`: four parameter sets (1/1, 3/24, 8/24, 16/32 entries /
  transactions) pass a directed fill/drain and 10000 random cycles each.
  Full internal next/current state and outputs match the original library.
  This is differential simulation, not a formal proof.
- `check_eth_shared_ddr.py`: all 72 shared-DDR protocol checks pass with the
  candidate, including independent masters, responses, protection and reset.
- `check_rtl.py --profile host_ethernet --allow-vendor-ip`: no non-vendor
  elaboration errors. Vendor IP remains outside this static check.

Local evidence is `/home/wangwy/fpga_runs/axi_remap_local_counts_20260927`
and `/home/wangwy/fpga_runs/eth_shared_local_counts_20260927`.
An independent paired Vivado 2020.1 OOC synthesis uses the same part, 3.333-ns
clock and source snapshot on Windows at
`D:/fpga_runs/axi_remap_local_counts_20260927`. Only the remap counter update
differs. It does not instantiate the vendor PHY/MIG or perform implementation;
its timing result cannot establish full-design timing acceptance.

## Paired synthesis result

Both isolated syntheses completed with Vivado 2020.1 on 2026-09-27. The
candidate is an improvement, **not a timing pass**:

| OOC variant | WNS (ns) | TNS (ns) | Setup failing endpoints | WHS (ns) | WPWS (ns) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original table | -1.265 | -2382.446 | 4341 | +0.071 | +1.391 |
| Per-entry counters | -0.832 | -588.760 | 3190 | +0.071 | +1.391 |

The baseline worst path reproduced the mux spill-register to remap counter
cone (18 levels, 4.588 ns estimated data delay). The candidate worst path is
now the loader isolate AW state through `allowed()` address-range arithmetic
to `bad_address_q` (20 levels, 4.155 ns). The next reported path is the AR
range-select path, at -0.631 ns. Inspect the alignment, burst-end calculation,
range and 4-KiB checks before any further change; protection must not be
weakened to improve timing. The first repair does not establish that all ID
table paths pass.

These are unplaced internal-path estimates with an ideal OOC clock source,
not numbers interchangeable with the full-design report. No full synthesis
has been rerun with the candidate, and no implementation was launched. The
vendor PHY/MIG hold/skew blockers are not present in this OOC wrapper and
remain unresolved in the full design. All full-design synthesis timing checks
must still pass before proceeding.

Paired summaries, setup paths and utilization reports are retained in the
Windows `ooc/baseline` and `ooc/candidate` directories above. Local copies use
the `baseline_` and `candidate_` prefixes in the local evidence directory.

## Address-protection repair

The next hypothesis targets the measured 20-level range-check path, without
changing protocol latency or permitting additional addresses. For an INCR
burst let `a` be its byte address, `s` its AxSIZE and `l` its AxLEN (beats minus
one). The final aligned beat must remain in the first beat's 4-KiB page:

```
floor((a mod 4096) / 2**s) + l <= 4096 / 2**s - 1
l <= ((~a) & 4095) >> s
```

For the accepted sizes 0 through 6, a case statement implements this as
seven short comparisons against constant slices of the complemented page
offset. Combined with `0x80000000 <= a < 0x100000000`, page containment also
guarantees the final byte cannot escape the DDR aperture (both aperture ends
are page aligned). This removes the 65-bit align/add/subtract sequence. Size
7, non-INCR bursts, locked accesses and write ATOPs are still rejected.

`check_eth_shared_ddr.py --range-check` compares the actual RTL function with
the original expression. All 17,009,984 cases passed: every page offset,
AxLEN and AxSIZE at both aperture boundary pages, all burst encodings at
selected legal/illegal addresses, and random full-address/inside-window
cases. This is a two-state input equivalence test, not a formal proof.
The 72 existing shared-DDR protocol checks and 33 exporter tests also pass;
static full-profile elaboration reports no non-vendor errors.

Evidence directories:

- `eth_shared_range_equiv_20260927`: function equivalence.
- `eth_shared_range_protocol_20260927`: protocol regression.
- `eth_shared_range_timing_20260927`: identical generic OOC wrappers comparing
  old/new range logic, with the per-entry remapper in both.
- `eth_shared_adapter_timing_20260927`: the same paired comparison with only
  the constant connections from `ara_eth_loader` applied (ID zero, 32-bit
  addresses, zero user/region/ATOP). Burst lengths/sizes remain variable.

The last comparison distinguishes paths that survive the actual adapter
connections from those retained only by an unrestricted generic wrapper.
Neither wrapper includes upstream DMA internals, vendor PHY/MIG, or real
clock skew. Neither can release the full-design synthesis timing gate.

Measured range-check comparison:

| Wrapper / version | WNS (ns) | TNS (ns) | Setup failing endpoints | LUTs |
| --- | ---: | ---: | ---: | ---: |
| Generic / old range | -0.832 | -588.760 | 3190 | 9763 |
| Generic / new range | -0.627 | -1331.217 | 3447 | 9837 |
| Adapter constants / old range | -0.231 | -48.959 | 249 | 6696 |
| Adapter constants / new range | -0.231 | -48.959 | 249 | 6594 |

All four had WHS +0.071 ns and WPWS +1.391 ns. The generic wrapper's TNS
regressed: do not describe this as a general timing improvement. Its worst
path now ends in the demux's 256-entry ID counter bank, while the actual
adapter fixes its request IDs to zero. The adapter-constant comparison shows
102 fewer LUTs with unchanged timing, and a different remaining critical
cone: AR spill -> read-table match encoding -> selected-entry full lookup ->
write-ID allocation -> write-table counter CE (13 levels, 3.468 ns).

## Parallel full lookup

The measured adapter-constant path still serializes match encoding and
counter-full selection. The next hypothesis is to compute per-entry
`match && full` terms in parallel with ID encoding. Priority qualification
retains the lowest-match behavior even if more than one entry matches. A
constant-input instance of the same `lzc` retains its exact empty-index
convention, including padded non-power-of-two tables, so even the nominally
don't-care `exists_full_o` output on a miss is unchanged for known inputs.

The experimental `axi_remap_fpga` applied local-counter and parallel-full
transforms; its restore operation produced the original library for tests.
Five parameter sets (including 5 entries / 3 transactions) pass 10000 random
cycles plus directed fill/drain each, checking all outputs and next/current
table state. The 72 shared-DDR protocol checks also pass. The paired OOC run
`eth_shared_fullflag_timing_20260927` uses adapter constants and new range
logic in both variants; only the full-lookup transform differs. Timing must
be evaluated from its final reports before claiming a benefit.

The parallel-full candidate did **not** improve the acceptance metrics:
WNS -0.231 -> -0.308 ns, TNS -48.959 -> -48.756 ns, setup failing endpoints
249 -> 442. Hold and pulse-width values were unchanged. Its worst path is
now AR spill -> match/priority tree -> `no_match` -> read-ID allocation ->
read-table counter CE (12 levels, 3.545 ns). Logic delay dropped from 0.919
to 0.813 ns but estimated routing rose from 2.549 to 2.732 ns. Fewer logic
levels alone are not an acceptance criterion.

A bounded follow-up, `eth_shared_directmatch_timing_20260927`, tests the
specific hypothesis that computing `no_match = ~(|match)` independently of
the encoder's empty output shortens that measured control path. It retains
the parallel-full candidate as its paired baseline. Five differential test
configurations and the 72 protocol checks pass. This experiment is not an
accepted timing repair; retain neither experimental lookup change if its
measured result is worse than the counter-only baseline.

The follow-up measured WNS -0.267 ns, TNS -35.385 ns and 363 failing setup
endpoints. Both lookup experiments were reverted; the retained helper again
changes only per-entry counters. Frozen experimental snapshots are preserved.

## Static source partition

Inspection of `board_cfg`, `gen_axi_in` and `CHESHIRE_TYPEDEF_AXI` showed that
the combined profile's LLC output ID is only **5 bits**: 2 master bits +
clog2(4 sources) + 1 LLC bit. The existing SoC-domain `axi_iw_converter`
zero-extends this to 8 bits before the CDC. The loader adapter sets ID to zero.
Thus the 9-to-8 dynamic remapper after `axi_mux` is unnecessary here.

The falsifiable hypothesis is that removing the dynamic ID lookup/allocation
from the UI domain removes the reported AR-spill-to-table-counter-CE path.
Keep the proven AXI mux, all five spill stages, protection and isolation.
In static mode encode `{source, input_id[6:0]}` into MIG's 8-bit ID; expand
responses to `{source, 1'b0, returned_id[6:0]}` before the mux. The removed
bit is structurally zero, not information loss. No new remapper or pipeline
is required in either clock domain. All channel sidebands remain unchanged.

The wrapper enables static partition only when `SocIdWidth < cfg.IdWidth`
and `cfg.IdWidth == 8`. Wider-ID configurations retain the original dynamic
path. Runtime assertions reject input bit 7 in static mode. Full-profile
static elaboration checks both the selected branch and the actual 5-bit ID.
Removing the dynamic allocator removes its 16-unique-ID/32-per-ID throttle;
AXI downstream backpressure and the existing mux/loader queue limits remain.
This is not claimed cycle-equivalent to the old allocator's ready timing.

Validation so far:

- `eth_shared_static_allids_20260927`: 584 checks, including all 128 IDs on
  both sources, overlapping same-ID transactions, bursts, strobes, firewall,
  isolation drain and reset.
- `eth_shared_static_reorder_20260927`: 32 outstanding reads and 32 writes,
  reverse-ID responses, independent B/R, 2-bit user/response sidebands and
  response backpressure.
- Five remap-table equivalence configurations and 33 exporter tests pass.
- Full-profile static elaboration confirms 5-bit source IDs, static branch,
  unchanged FIFO widths and no non-vendor errors. Vendor IP is not elaborated.

`eth_shared_static_timing_20260927` compares dynamic/static modes under the
same 3.333-ns OOC clock and loader constants. These remain module-only results,
not complete-design setup/hold/skew acceptance. No implementation is launched.
The frozen combined runner now defaults to `-Stage synth`, with an explicit
synthesis-only completion state, in addition to the strict timing gate.

The static partition OOC comparison completed successfully:

| Mode | WNS (ns) | TNS (ns) | Failing setup | WHS (ns) | WPWS (ns) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dynamic | -0.231 | -48.959 | 249 | +0.071 | +1.391 |
| Static | +0.331 | 0.000 | 0 | +0.071 | +1.391 |

This resolves the measured module-only setup failure, not the full build.
The 72 dynamic-mode protocol regression checks also pass. Windows mock tests
exercise synthesis-only default/explicit mode and rejection; 42 Tcl managed
flow tests retain the strict setup/hold/pulse-width gate. No vendor clock
constraints, jitter, PHY internals or MIG configuration were changed.

The candidate's worst remaining OOC setup path is the protection demux's
AW in-flight counter to AW spill-register CE: 10 levels, 2.906 ns data delay.
The dynamic remap-table path is absent. LUTs fall from 6594 to 3941 and FFs
from 6727 to 4692 in this comparison.

A new immutable full-profile synthesis-only run has been started at
`D:/fpga_runs/ara_static_ids_synth_20260927_0057`, independently of SSH.
The 865-file snapshot passed verification; PID 17776 reached `prepare_ip`
with Vivado PID 672 at 2026-09-27 15:58 (+08:00). Invocation explicitly uses
`run_combined.ps1 -Stage synth`. Inventory SHA256 is
`758f5a1adebb436f30b6fb8344e9edd360c30762e53959ea96825dbb4ad83b20`.
The user subsequently required PHY hold and MIG skew resolution BEFORE any
new full synthesis. This new run was stopped during `prepare_ip` at 15:59
(+08:00), before full synthesis, with its owned process tree terminated.
Its state is `stopped_pending_phy_hold_mig_skew`; preserve the partial bundle,
do not resume it. The original snapshot and board are untouched. No new
full-profile timing result is available. Do not start another full synthesis
until the two remaining issues are resolved under the user's acceptance policy.

The other two issues have been classified, not repaired: the old full-profile
PHY hold and MIG internal skew reports remain failing evidence. Current source
review has not identified an incorrect user clock constraint that could be
honestly corrected to resolve them before physical implementation. Do not
claim that the new AXI repair fixes them, or promise that all unplaced hold
checks can be made nonnegative through RTL edits. Under the current hard gate,
their continued failure must stop the new flow without implementation.
