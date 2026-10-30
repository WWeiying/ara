# Canonical AKV Runtime RTL Acceptance

The shared-head Decode and F32 Prefill-PV leaves are already compiled from the
canonical AKV C/assembly source. They remain opt-in and default off. Compiled
object equivalence and an accepted experimental ELF do not by themselves prove
that the newly integrated source was rebuilt and executed correctly.

`build_live_regression.py` therefore recompiles all runtime/test/common/data
objects from current canonical source while retaining the accepted original
stimulus. It does not reuse old runtime objects. Exactly two intentionally
superseded historical canonical files are resolved to their fixed pre-promotion
snapshots for provenance; every other historical input must still match.
New execution uses independent output directories and the accepted RTL image.

## Independently Accepted Decode

`verification/out/akv-live-decode-20261024-01` completed actual VCS execution with
zero exit and a clean worker PASS. A separate replay audit is in
`verification/out/akv-live-decode-audit-20261024-01`.

| D | Query heads in group | Visible tokens | Mode order | Result |
|---:|---:|---:|---|---|
| 64 | 3 | 1 | OFF / ON / OFF | PASS |
| 96 | 3 | 65 | OFF / ON / OFF | PASS |
| 128 | 6 | 7 | OFF / ON / OFF | PASS, original six-head specialization retained |
| 128 | 2 | 64 | OFF / ON / OFF | PASS |

The audit rechecks current source/tool/data/image identities, actual raw command
records, all 12 calls, 3,680 AKV commands, complete 4,096-word output buffers
including padding checks, FP/vector CSR state, and independent backend/AXI
read/write protocol evidence. Each case's output checksum and CSR signature is
also identical to its fixed pre-promotion candidate evidence.

The old experimental worker that failed because of document drift is not
relabeled. Historical evidence is used only for explicitly scoped numerical
comparison; it is not asserted that historical canonical source pins equal
the current integrated source. The new worker's own source pins and execution
must independently pass without any document/code exception.

Tracked receipt:
`verification/akv/results/canonical-decode-runtime-20261024.json`.
Audit entry point: `audit_live_regression.py`.

## Independently Accepted Prefill

`verification/out/akv-live-prefill-20261024-01` also completed with clean PASS;
the automatically event-gated independent audit completed in
`verification/out/akv-live-prefill-audit-20261024-01`.

This is the real SmolLM2-135M capture slice at original Query positions32--35,
all nine Query heads/three KV heads, D64, 2,304 outputs per call. ABBA cycles
were 202,315 / 190,069 / 190,352 / 201,779: generic canonical AKV totals404,094
and paired F32 PV totals380,421, a5.8583% cycle reduction (1.06223x).
This ratio compares generic and paired AKV, not ordinary RVV or full models.

All four calls, 13,380 AKV commands, original golden tolerance, exact
generic/paired output bits and CSR state, source/image pins, actual exit and
independent backend/AXI checks passed. Numerical signatures also match the
fixed pre-promotion candidate. Tracked receipt:
`verification/akv/results/canonical-prefill-runtime-20261024.json`.

## Remaining Boundaries

- Decode and Prefill were checked independently; neither acceptance substitutes
  for the other's data, layout, numerical or protocol checks.
- These Decode functional tests do not print a task-cycle performance result.
  Earlier accepted speedups remain separate experiments, not fresh measurements
  attributed to this regression.
- This is native-function execution on derived real model data, not a full
  GGML graph, whole-model execution, or exhaustive shape/feature coverage.
- Existing RVV/F16 fallback paths and default-off switches remain in place.
  Quantized-KV Attention is a separate candidate with separate numerical gates.
