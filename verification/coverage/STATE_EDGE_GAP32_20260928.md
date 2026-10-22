# QBS/AKV state-edge closure, 2026-09-28

**Later same-day update:** The QBS compute `WAIT_WEIGHT`, wide-context,
multi-block, fault-phase and reset stimuli were extended on a newer coverage
image. The latest local PASS-only result and remaining gaps are recorded in
`GAP_CLOSURE_20260928.md`. The historical counts below describe the earlier
image and must not be treated as the current endpoint.

## Scope

The verification-only reset trigger now asserts reset at the falling edge
while the requested engine state is still present. The previous trigger
sampled a rising edge and waited another half cycle; one-cycle states could
advance before reset. The marker records the actual sampled state, and the
normal (no plusarg) testbench behavior is unchanged. No DUT RTL was edited.

The new coverage image is
`verification/out/state-edge-coverage-20260928-02/sim/simv` with QBS, AKV-v2,
AXI delay and VCS line/condition/FSM/toggle/branch coverage enabled. The
source manifest passed after compilation and before every run. All 18 tests
used this image, separate output directories, independent application
self-checks and the CVXIF/VID/AXI UVM audit. Every test reported PASS and
produced its own `code.vdb`.

## Measured result

| Scope | Before, 18 old-trigger tests | After, 18 corrected-trigger tests |
| --- | ---: | ---: |
| QBS main `state_q` | 28/30 | 30/30 |
| AKV main `state_q` | 33/36 | 36/36 |
| DVE top raw Score | 43.09% | 43.16% |
| DVE top raw FSM | 18.80% | 19.14% |

The five newly covered reset transitions are QBS
`DESCRIPTOR_REQUEST -> IDLE`, `VALIDATE -> IDLE`, and AKV
`DESCRIPTOR_REQUEST -> IDLE`, `REPLAY_READ -> IDLE`, `VALIDATE -> IDLE`.
The per-instance FSM bits were checked directly with
`inspect_fsm_gaps.py`; the complete merged report is
`verification/out/state-edge-full-dve-20260928-02/summary.csv`. The first
DVE attempt in `state-edge-full-dve-20260928-01` failed at launch with an
empty log and produced no report; the second attempt completed. The reviewed
waiver set does not match this image (`NOT_APPLICABLE_UNREVIEWED_DESIGN`), so
only the raw numbers above are reported.

This closes the **main engine state_q** gaps, not every descendant FSM or
design-wide coverage gap. In the same 18-test report, QBS `i_compute_engine`
has 22/43 `state_q` points; its untested multi-context/tile and fault-phase
edges need separate legal workload selection. QBS module aggregate FSM is
37.80% and AKV module aggregate FSM is 96.97%; neither percentage is the
main `state_q` ratio. The top-level 18-test score must not be compared with
the earlier 510-PASS frozen-image score as if they were the same suite or RTL.

Three additional PASS tests used the same image: a real Qwen2.5 QBS slice
with `K=1536`, 32 output rows and four inputs, `sv39_state_prereq`, and
`linux_vector_context`. Their 21-test raw report is
`verification/out/state-edge-extended-dve-20260928-01/summary.csv`: top
Score 46.90%, QBS compute `state_q` 25/43. The real-data slice exercises
`QBS_CLEAR_BLOCK`; the two short system tests do not constitute a Linux boot.

The additional real-data `M=8` test in
`apps/llama_qwen25_shape_prefill_m8_cov_qbs` uses the same captured Qwen2.5
Q4_K tensor, `K=1536`, eight output rows and eight input vectors. It is
small enough for a bounded RTL run but satisfies the hardware's `M>=5`
wide-command condition. Application self-check and UVM audit passed. The
22-test raw report is
`verification/out/state-edge-wide-dve-20260928-01/summary.csv`:

| Metric | 18 directed tests | 21 tests | 22 tests including M=8 |
| --- | ---: | ---: | ---: |
| Top Score | 43.16% | 46.90% | 47.73% |
| Top FSM | 19.14% | 26.35% | 26.55% |
| QBS module FSM | 37.80% | 55.51% | 56.30% |
| QBS compute `state_q` | 22/43 | 25/43 | 28/43 |
| AKV main `state_q` | 36/36 | 36/36 | 36/36 |

The M=8 VDB confirms `QBS_COMPUTE_TILE -> QBS_START_CONTEXT_WAVE` and the
return to compute. `QBS_WAIT_WEIGHT` remains unvisited: the observed workload
did not make weight delivery late enough to enter that waiting state. Do not
force that state by changing a performance parameter without a bounded,
cycle-level hypothesis.

## Remaining signoff work

### Short QBS compute-phase stimuli

The separate coverage image at
`verification/out/qbs-child-reset-20260928-01/sim/simv` adds five PASS
cases. `qbs_two_block_phase_cov` issues one legal Q4_K x Q8_K command with
two K blocks, checks the 512.0 result and unchanged tail, and exercises
`QBS_COMPUTE_TILE -> QBS_CLEAR_BLOCK` without a long model slice. Four
`qbs_reset_read_cov` replays assert reset at the falling edge while the
compute child FSM is respectively in `QBS_INIT`, `QBS_LOAD_TILE`,
`QBS_COMPUTE_TILE`, or `QBS_FINAL_DRAIN`. The testbench prints the actual
sampled state before reset. Each replay passed application self-check and
the CVXIF/VID/AXI UVM audit after restarting.

The five compatible VDBs were merged in
`verification/out/qbs-child-reset-20260928-01/dve/summary.csv`. Direct FSM
inspection reports QBS compute `state_q` at 19/43 points, including the four
targeted reset-to-IDLE transitions. This is a five-case local result, not an
update to the historical 510-case score or the separate 22-case image.
The remaining child-FSM gaps include `WAIT_WEIGHT`, its start-weight path,
fault drain/clear, and reset from `CLEAR_BLOCK` and the wide-context phase.
Those require their own legal phase-specific stimulus and measured timing;
do not force them by changing DUT performance parameters solely for coverage.

- Re-run these five cases on the eventual full-suite image before merging
  coverage; VDBs from different compilations are not interchangeable.
- Re-run the larger PASS suite on a single current-RTL image before publishing
  a current design-wide coverage figure. The historical 510-test report is
  from a different frozen image and cannot be merged here.
- Use a legal context-reuse or delayed-weight workload to test QBS
  `WAIT_WEIGHT`, then use a phase-targeted fault to test the compute-engine
  fault edges. The completed M=8 and 32-row cases cover the ordinary wide
  and multi-block paths, but the compute engine still has 15 uncovered
  `state_q` points. Reset/default edges need separately audited reset tests.
- Analyze Dispatcher overlap/flush/store-response gaps with controlled
  interface stimuli. Do not infer they are unreachable from the 18 tests.
- The FP16 RNE case at `verification/out/fp16-rne-current-20260928-01`
  failed three architectural self-checks. It remains excluded from PASS-only
  coverage pending first-mismatch localization and correction.
- Review PTW virtualization-stage gaps against the SoC's disabled RVH and
  `NrPMPEntries=0` configuration. The 22-test PTW `state_q` is 13/26 while
  `ptw_stage_q` is 0/9; the latter is inactive with RVH disabled. Do not
  generate invalid traffic merely to raise a coverage percentage; any waiver
  requires a reviewed reachability argument for the exact point.
