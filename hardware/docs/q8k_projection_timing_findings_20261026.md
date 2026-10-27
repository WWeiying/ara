# Decode preparation and context reuse: current timing findings

## Complete single-output projection

Run: `verification/out/q8k-decode-projection-groupcheck-20261026-01`.
The application completed four ABBA trials and reported zero errors. The
independent QEMU output digest and FCSR/VCSR agree with every RTL trial.

| Trial | Quantizer | Preparation | Execution | Total |
| --- | --- | ---: | ---: | ---: |
| 0 | Original | 9975 | 112913 | 122888 |
| 1 | Layout candidate | 8708 | 112806 | 121514 |
| 2 | Layout candidate | 8600 | 112819 | 121419 |
| 3 | Original | 9874 | 112843 | 122717 |

Paired totals are 245605 versus 242933 cycles: 1.010999x, or a 1.0879%
cycle reduction. Preparation decreases from 19849 to 17308 cycles, 12.8017%,
but preparation was only about 8.08% of the original projection cycles.
Execution is essentially unchanged. Thus the preparation-only improvement
must not be presented as a comparable complete-projection speedup.

The formal worker result remains FAIL: its detailed UVM/contract event
streams were limited to 100000 entries while the monitored run completed
190331 requests and 167747 backend allocations. All four reported issues are
event-stream incompleteness/disagreement. The continuous monitors report zero
errors; requests, backend instructions and AXI transactions are drained.
This does not recover missing detailed events or justify changing formal
signoff to PASS.

`audit_completed_projection.py` independently verifies the original input
pins, the exact issue scope, closed activity, complete application results,
and the QEMU comparison. It creates `functional-timing-audit.json` with state
`FUNCTIONAL_TIMING_COMPLETE_EVENT_AUDIT_INCOMPLETE`, leaving the original
FAIL reports untouched. Log SHA256:
`10fe0ea2b36c5812f3cc67887ad3407c33891d4b786f8e0661d65739ef5e70e0`.

## Mixed-profile Q/V/K projection reuse

Run: `verification/out/q8k-context-qkv-groupcheck-20261026-01`.
Only the first three trial records are complete:

| Trial | Reuse | Preparation | Execution | Total |
| --- | --- | ---: | ---: | ---: |
| 0 | Off | 29561 | 158184 | 187924 |
| 1 | On | 9822 | 157723 | 167671 |
| 2 | On | 9831 | 157566 | 167510 |

These records have equal output digest and CSR and show reduced preparation
work. The process hit its wall-time limit before the complete ABBA group and
final integrity/result marker. They are partial observations, not a completed
paired result or production acceptance. No formal speedup is assigned.

## Next acceptance action

Do not weaken the strict UVM checker or install runtime candidates on the
strength of these incomplete gates. Configure sufficient event capacity in
the successor before launch. Replace CPU-executed weight hashing with a
bounded, exact vector comparison against an independent read-only image copy,
or another independently checked method that does not dominate simulation.
Retain actual Q/V/K profiles and dimensions, numerical oracles, canaries,
matched ABBA timing and a bounded wall-time budget. Then repeat the complete
gate and integrate only a confirmed beneficial candidate.
