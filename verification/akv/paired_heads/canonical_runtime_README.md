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

## Remaining Boundaries

- The canonical Prefill runtime has a separate running regression and requires
  its own terminal execution and independent audit. Decode PASS does not cover it.
- These Decode functional tests do not print a task-cycle performance result.
  Earlier accepted speedups remain separate experiments, not fresh measurements
  attributed to this regression.
- This is native-function execution on derived real model data, not a full
  GGML graph, whole-model execution, or exhaustive shape/feature coverage.
- Existing RVV/F16 fallback paths and default-off switches remain in place.
  Quantized-KV Attention is a separate candidate with separate numerical gates.
