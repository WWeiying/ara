# Last-dot retirement candidate

## Exact change

`retire_candidate.sv` is a test-only copy of the current integer engine.
It adds a completion alternative: issue and s0 are empty, only the final dot
metadata stage is valid, dot data is valid, and that result belongs to the
current compute context. On that edge the existing dot accumulation still
executes; compute-active clears and done registers concurrently. No new start
is allowed on that same edge. On the next edge dot data and metadata are empty.
An added assertion checks this property when done is observed.

No context-valid clearing, correction handling, result-ready rule, narrow-tail
guard, dot latency or arithmetic is changed. This is not two simultaneous
integer-tile issues or a replacement of final context release by input release.
Bank changes remain under the original parent's done-driven FSM.

## Local VCS evidence

The baseline and candidate were compiled independently using the same engine
Makefile, standalone composition generator and testbench. `candidate.mk`
substitutes only the integer-engine source in the compile inventory. Production
RTL files are unchanged. The generator's `generation.json` describes the
canonical composition, not a claim that its production integer module was used;
the VCS compile log records the actual candidate replacement.

| Run | Functional cases | Response gap | Additional checks |
| --- | ---: | ---: | --- |
| Baseline `baseline-full.log` | 36 | 0 | Four atomic fault classes, context lifecycle, next-block fault/reset replay |
| Candidate `candidate.log` | 36 | 0 | Same checks, plus bounded boundary probe |
| Candidate `candidate-gap3.log` | 36 | 3 | Same checks with spaced read responses |

All three logs pass the independent existing
`run_tile_context_engine.check_log(text,36,1,gap)` parser. Its context count is
one for this vector set; this does not claim capacity-wide context coverage.
Four fault classes are validation, MMU, AXI and PMA. The numerical suite also
includes M>4 tail waves and all nine supported profiles, but the bounded probe
does not itself cover every tail or profile.

For gap=0, per-case configuration tuples match exactly. Of 36 cases, 34 are
faster and two unchanged; none slower. Summed case cycles are 30667 baseline
and 30179 candidate (1.59% reduction). This sum is a diagnostic collection of
different shapes, not a workload-weighted benchmark or model performance.
No matched gap=3 baseline performance comparison is claimed.

The first observed boundary changes from last-read/done/start/new-read offsets
0/6/7/8 to 0/5/6/7. The old context remains live, and correction is still in
flight. Thus the measured one-cycle saving matches the intended completion
change without premature context release in the observed windows.

Evidence under `verification/out/`:

- Baseline build: `qbs-tile-boundary-build-20261029-01`.
- Candidate build: `qbs-retire-boundary-build-20261029-01`.
- Baseline log SHA256: `fb77599edc64eb12c94f576aaadbf2c7431f2b0824d1042f8c5e3ed2d349501e`.
- Candidate log SHA256: `431de651dc1b77a466e7aa683f653ec1bbd79915d278e149ccf9a1f3c6bf59a8`.
- Candidate gap3 log SHA256: `5258d60b3ec2b290dee63ee09b96eae5287236d679aff7b6a6e3ff28f251aeba`.

## Capacity, pressure and fault completion gates

The candidate also passed the 448-case profile suite with
`+QBS_STALL_RESULTS`. This drives the existing deterministic LFSR/result-ready
gate; every case checks first and repeated integer/FP results and fflags.
It covers nine profiles, M=1..4 and output-row counts 1..4. The original
36-command engine suite additionally includes M=5/6/7/8 waves, including a
short subgroup-16 tail, without changing the existing correction-drain guard.

The capacity suite has 12 shapes: Q4_K and Q8_0, M=1/4/5/6/7/8, N=5 and the
largest supported K-block count that fits the saved activation tile. The
candidate passed gap=0, including FILL/REUSE/RELEASE, all six weight-fault
retry combinations and next-block fault/reset recovery per shape.

The unmodified capacity suite at gap=3 failed on BOTH baseline and candidate:
case 1 (Q4_K M4 Kb4), REUSE, AXI response fault, at the assertion requiring
the fault to interrupt active replay. This failure is retained, not counted
as PASS. The observation-only baseline run provides the distinguishing events:

| Cycle | Observation |
| ---: | --- |
| 90195 | First AXI R error response; replay still busy |
| 90265 | Replay finishes |
| 90336 | Read-engine fault becomes visible after burst drain |

Thus the assertion's timing precondition does not hold at this response gap;
the original log does not prove a functional fault/recovery failure.

`replay_probe.sv` adds a separate, opt-in `+QBS_FAULT_REPLAY_HOLD` experiment.
It forces the compute receiver's activation-ready low only during injected
AXI context faults, before any replay can finish. Both adapter write-valid
inputs are asserted low while held. Fault arrival releases the hold; the
original bench, its mandatory-overlap assertion and all numerical/fault/retry
checks remain unchanged. No RTL input data, arithmetic or context state is
forced. It is a receiver-pressure test, not a performance benchmark.

With gap=3 and this pressure, BOTH baseline and candidate pass all 12 shapes,
with exactly 24 holds, 24 fault/replay overlaps and no outstanding hold at end.
The strict collector reuses `run_tile_context_engine.check_log/check_geometry`
and rejects missing, duplicate or failed cases. Additional mutation tests
check exact profile geometry and complete held-replay accounting.

New evidence under `verification/out/`:

- `qbs-retire-profile-build-20261029-01/profile-stalls.log`: 448 cases.
- `qbs-retire-boundary-build-20261029-01/candidate-context.log`: gap=0 capacity.
- `qbs-baseline-replay-build-20261029-01/baseline-context-gap3-trace.log`:
  original precondition failure with cycle evidence.
- `qbs-baseline-replay-build-20261029-01/baseline-context-gap3-held.log`.
- `qbs-retire-replay-build-20261029-01/candidate-context-gap3-held.log`.
- `qbs-retire-replay-build-20261029-01/local-gates.json`: checked cases and
  SHA256 evidence pins; explicitly not a complete compile-source inventory.

## Production-source admission and remaining gate

After the above gates, the integer-engine change is copied exactly to the
verification branch's `hardware/src/vlsu/qbs/qbs_profile_engine_int.sv`.
The isolated candidate remains as the exact tested reference. This is source
admission for fresh SoC validation, not a claim of final performance acceptance.
The main `ara_dsa` worktree is untouched.

Next: compile a fresh canonical SoC image, revalidate ordinary RVV/coexistence
and compare the same real projection binary against the baseline evidence.
Any hardware performance claim must come from that matched binary/configuration
pair. No synthesis, timing or area improvement is established here.
