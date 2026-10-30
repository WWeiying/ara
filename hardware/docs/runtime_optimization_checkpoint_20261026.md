# Runtime optimization checkpoint

## Complete-call decision

The grouped-PV candidate passes the bounded same-ELF Attention ABBA check,
but it is not a performance improvement. Parent review replayed the existing
checker against the raw VCS log and golden data, verified the source pins,
and reproduced the worker's entire raw-check result.

| Mode | First call | Second call | Sum |
| --- | ---: | ---: | ---: |
| OFF | 480064 | 479632 | 959696 |
| ON | 490982 | 491371 | 982353 |

ON takes 2.3609% more cycles. Native QBS busy time remains 8804--8805 cycles
per call. This supports investigating the software execution path, but does
not distinguish instruction count, dependency chains, or memory stalls.
Do not infer a specific root cause without additional evidence. Keep the
candidate default OFF. These are complete Attention-call measurements,
not end-to-end model measurements or a new RVV-versus-QBS comparison.

Receipt: `verification/akv/results/grouped-pv-pair-review-20261026.json`.
The numerical comparison runs on target against the full golden output;
the compact UART digest is not a separate host recomputation of all values.

## Q8_K production dispatch gate

The private combined-Zvfh Q8_K candidate has passed its numerical gate.
The next actual-GGML graph run was launched as
`q8k-combined-graphs-20261026-01.service`. It terminated before arithmetic
at `extended_context_capability_required`, in OFF mode, first graph.
It must not be reported as 384 graphs executed or as a numerical mismatch.

Original evidence remains in
`verification/qbs/combined_zvfh_m4/graphs/run-01/`.
The test requires an extended activation-context capability contract;
the exact mismatching field and compatible model need investigation.
Do not suppress the check or relabel this run. Use a separately identified
successor after verifying the model, SDK and intended test contract agree.

The next performance decision remains the complete projection call using
real inputs and current RTL. QEMU results can establish functional dispatch,
not speedup. Production defaults, Q8_0 selection and RTL remain unchanged.
