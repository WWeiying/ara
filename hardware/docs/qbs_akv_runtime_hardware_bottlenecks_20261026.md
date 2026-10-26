# QBS / AKV Runtime Hardware Bottlenecks: 2026-10-26 Review

## Decision And Scope

Do not change RTL on the present evidence. No new arithmetic array, FP table,
reader queue, SRAM port, or weaker ownership barrier is justified for improving
the measured complete quantized-Attention call. Command pre-drain is worth
investigating only if future measurements establish a substantial avoidable
delay outside the existing busy counter.

This records a read-only review of `ara_dsa_signoff_integration`, at revision
`d0c0f8c5`, and results dated 2026-10-23 through 2026-10-26. The inspected
dispatcher, VLSU, QBS engine/compute/FP/reader, shared-reader and AKV-engine
sources match the candidate run's source pins. No RTL, runtime policy, checker,
sealed helper or existing result is changed by this document.

The future measurement ideas below are NOT new requirements for this round.
They do not authorize a probe implementation, image build, EDA launch, long
simulation, synthesis, or model campaign. Existing model-run pins are unchanged.

## Accepted Workload And Counter Meaning

The [fresh paired result](../../verification/akv/quantized_kv/field_copy_pair/RESULTS.md)
uses real Q4_0 K / Q8_0 V, six query heads, D128 and 128 visible tokens in one
selected KV-head group. Each executable runs H/S/B/B/S/H. B performs QK through
QBS DIRECT and the remaining Attention work through software/RVV; B is NOT the
F16 AKV command path. This is a complete call for the captured group, not a
complete layer or model.

Candidate B takes 476050 and 475661 cycles, totaling 951711. Its sixteen QBS
commands report 17609 busy cycles in total. Baseline busy is also 17609 despite
the software change reducing complete B cycles from 1137762 to 951711 (16.35%).

The actual definition is:

- In [qbs_engine.sv](../src/vlsu/qbs/qbs_engine.sv), `busy_o` means
  `state_q != QBS_ENGINE_IDLE`; `command_ready_o` means IDLE.
- `command_cycles_o` clears on `command_fire`, then increments while busy.
- In [vlsu.sv](../src/vlsu/vlsu.sv), the terminal `QBS_PERF` record prints
  `command_cycles + 1`. Its busy interval includes descriptor fetch/validation,
  activation/weight handling, computation, drain, commit and terminal handling.
- Busy is neither pure integer-dot time nor general FPGA/CPU utilization.
  Dispatcher/ownership waiting BEFORE command acceptance is not included.

## Actual Phase Evidence

The following are sums over the candidate's same sixteen native commands,
recomputed from `raw_replay.hardware_records` in
`verification/out/field-copy-candidate-20261026-01/result.json`:

| Exclusive command phase | Cycles |
| --- | ---: |
| Setup | 241 |
| Activation | 384 |
| Weight | 6408 |
| Compute | 1168 |
| Compute/read overlap | 8048 |
| Drain | 352 |
| Scheduler | 592 |
| Commit | 400 |
| Fault | 0 |
| Terminal | 16 |
| Total | 17609 |

These phases partition the controller's busy interval. In particular, the
overlap label means compute state with reader activity; it is not an additional
stall category. Other diagnostic probes are not a second exclusive partition.

Additional observations from those records:

- FP table-full, FP slot/accumulator blocking and profile-result blocking are
  all zero. Per-command FP table occupancy peaks at 8; summing occupancy maxima
  across commands is not a capacity measurement.
- Reader R backpressure and AR-ready-blocked probes are zero. The observed
  per-command maximum outstanding count is 2, not the sum of sixteen maxima.
- Strict `QBS_WAIT_WEIGHT` totals 4824 cycles: 896 with no outstanding burst,
  2008 with an outstanding burst but no R-valid, 1920 transferring R, and zero
  R-blocked. This exclusive wait-state split is not all reader occupancy.
- `probe_read_response_idle_cycles=7081` and
  `read_outstanding_full_cycles=6552` overlap other activity. Do not add them to
  the phase table or equate them with removable complete-call stalls.
- `fp_uop_issue=18432` counts micro-operations across issue ports, not cycles.
  Existing split and finite-half issue optimizations are already enabled.

The probe predicates are in
[qbs_compute_engine.sv](../src/vlsu/qbs/qbs_compute_engine.sv),
[qbs_engine.sv](../src/vlsu/qbs/qbs_engine.sv), and
[qbs_read_engine.sv](../src/vlsu/qbs/qbs_read_engine.sv).

## Conditional Maximum Benefit Budget

For this pair of B calls:

```text
T_full     = 951711
T_busy     =  17609
T_residual = 934102
busy fraction = 1.8502466%
```

If ONLY the already-counted busy interval changes and all other timing remains
unchanged, eliminating ALL of it would give at most
`951711 / 934102 = 1.0188513x` speedup, or 1.8502% fewer cycles. Halving it
would give `1.0093376x`, or 0.9251% fewer cycles. Zero command latency is an
unattainable optimistic budget, not an optimization forecast.

**934102 is a residual outside the command-busy interval, NOT an all-software
cost or an exclusive CPU-stall classification.** It can include software
instruction execution, ordinary RVV computation/memory latency, command-front
waiting, and other synchronization. The busy-only budget does not bound an
optimization that also changes those intervals, cache behavior or frequency.

The previous three-call phase/copy audit used an older program. Its function
gap counts cannot be transplanted onto the post-field-copy candidate to claim
an exact current PV, exponential, decode or admission breakdown.

## Conditional Hardware Investigation: Pre-Drain

[ara_dispatcher.sv](../src/ara_dispatcher.sv) waits for `ara_idle_i` before
issuing QBEXEC. [vlsu.sv](../src/vlsu/vlsu.sv) then requires
`normal_vlsu_idle`: address/load/store units idle, no preparation in flight,
empty AR hold, and drained normal/external AXI request/response cuts. QBS owns
VLSU and result interfaces exclusively until terminal completion.

Falsifiable hypothesis: some command-front waiting exceeds the real older-work
dependencies and contributes materially to the complete-call ROI. Current busy
records do not prove this hypothesis and cannot quantify its benefit.

If separately authorized later, observe one representative adjacent M4/M2 pair
using the actual current program/data and a bounded waveform window. Required
signals and timing points are:

- First stable front-end QBEXEC presentation: dispatcher `acc_req_i.req_valid`
  and decoded instruction; dispatcher state, `ara_idle_i`, request valid/ready.
- VLSU admission: `pe_req_valid_i`, operation/id, `qbs_command_valid`,
  `qbs_command_ready`, `qbs_command_fire`, `normal_vlsu_idle`.
- Reasons for admission delay: `addrgen_idle`, `vldu_idle`, `vstu_idle`,
  `prepare_inflight`, `ar_hold_empty`, relevant AXI AR/AW/W/R/B valid/ready,
  `core_st_pending_i`, and outstanding work/VRF destination dependencies.
- Engine interval: QBS state, `qbs_active_q`, `qbs_busy`, command-cycle counter,
  reader planner state, burst count, held AR, response-drain/fault state.
- Completion: `qbs_terminal`, LDU result request/grant AND final-grant,
  dispatcher response/exception/fflags, and architectural retirement when
  available. Initial grant is not proof of final architectural completion.

Separate first-presentation-to-command-fire, command-fire-to-terminal, and
terminal-to-retirement intervals. Calibrate edge counting against the RTL's
terminal `+1` convention. Do not sum overlapping wait predicates. The existing
200-cycle `QBS_ROOT_TRACE` begins at integer-tile launch, so it cannot by itself
explain pre-admission waiting.

Reject the hypothesis if the interval is small or explained by necessary older
work. Do not simply replace all-Ara drain with LSU-only idle: older arithmetic,
VRF writes, exceptions and FCSR ordering still need proof. No ownership barrier
change is approved by this review.

## Lower-Priority Planner Bubble

The reader takes `PLAN_IDLE -> PLAN_WAIT_STORE -> PLAN_TRANSLATE` for each new
nonempty range. `store_wait_cycles` increments only when WAIT_STORE coincides
with `core_st_pending_i`. Thus zero store-wait count does not eliminate the
unconditional state-transition bubble.

A future study could ask whether one bubble can safely be bypassed when prior
stores are demonstrably drained. For the current 2256 ranges, one cycle per
range is only a direct scheduling budget of 2256 cycles, 0.2370% of complete B.
Overlap may hide savings; this is not a guaranteed complete-call improvement.
Checking pending stores earlier can also miss a newly visible older store, so
the ordering/MMU/PMA/held-AR fault contract cannot be assumed unchanged.

This is not a reason to launch a new experiment now. Reusing existing datapaths
and adding no storage does not establish unchanged gate area or timing; no PPA
measurement has been made.

## Prior Results And Acceptance Boundary

- [REFILL overlap, 2026-10-23](../../verification/akv/results/refill-attention-abba-20261023.json):
  same-ELF, fixed-address complete Attention totals 214166 serial versus 217475
  overlap cycles, 1.545% slower. Focused overlap success did not imply call gain.
- [QBACC stripes, 2026-10-23](qbs_vrf_continuation_design.md): logical read
  payload fell about 7.36%, but the complete matrix region slowed 8.89% because
  repeated commands, commits, seed handling and replay mattered. Keep it OFF.
- [Split issue](qbs_fp_split_issue.md): removing 784 M1 slot-blocked cycles
  yielded only ten fewer command cycles. A disappearing probe is not a latency
  reduction of the same magnitude.
- [PANEL4, 2026-10-24](../../verification/akv/results/qk-panel4-attention-20261024.json):
  an existing F16 opt-in reduced command count and complete-call cycles by
  3.81%. This is not evidence for new quantized AKV hardware or global default
  enablement.
- [Field-copy pair, 2026-10-26](../../verification/akv/quantized_kv/field_copy_pair/RESULTS.md):
  16.35% fewer B cycles with unchanged QBS busy supports prioritizing current
  compiled software/RVV attribution before expanding QBS resources.

Only after static analysis and a discriminating measurement agree should a
minimal RTL change be proposed. A later hardware comparison must use the same
ELF/data and complete six-call checks on reviewed images, preserve numerical,
work, guard, FCSR/VCSR and independent UVM gates, and retain ordinary RVV and
held-AR fault/recovery regressions. These are future acceptance principles,
not additional mandatory runs for the present round.
