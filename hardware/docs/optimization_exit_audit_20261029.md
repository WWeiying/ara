# Optimization exit audit

This records execution of `optimization_exit_criteria_20261029.md`, not a
declaration that every gate is closed.

## Completed decisions

All four V-reuse services have reached terminal state. The copy pair timed
out and is not accepted. The pointer pair passed functional and protocol
checks but regressed 3.835733%/4.269561%; both candidates are rejected.
See `verification/akv/quantized_kv/prefill/VALUE_REUSE_DECISION.md`.
No additional cache variant is authorized by this closing work.

Earlier cache-hint and query-guard candidates were likewise rejected. Their
decisions remain in `verification/qbs/cache_hint/DECISION.md` and
`verification/akv/quantized_kv/prefill/QUERY_GUARD_DECISION.md`.

## Retained improvements and correct denominators

| Retained item | Accepted comparison | Scope |
|---|---|---|
| Parallel M4 preparation | 76060 / 44443 = 1.711406x | Preparation only |
| Parallel M4 sums plus final-dot retirement | 582799.5 / 547856 = 1.063782x | Complete Q/V/K slice, baseline already uses QBS |
| Register-PV Decode | 47885.5 / 43075.5 = 1.111664x | Guarded real Qwen3 Decode slice |
| Grouped Prefill Q4_0 K | 174314.5 / 147469 = 1.182042x | Four-query causal slice |
| Grouped Prefill Q8_0 K | 179726 / 148884.5 = 1.207151x | Four-query causal slice |

The projection comparator was rerun against the original records and their
record hashes. Retirement alone saves exactly 3008 cycles in every matched
trial: original sums 582799.5 to 579791.5, parallel sums 550864 to 547856.
The 1.058292x field inside the new-image projection report compares software
variants on that image; it is not the combined old-image/original-software
to new-image/parallel-software ratio. Do not multiply unrelated ratios or
present preparation speedup as full projection or model speedup.

## Current source versus historical test source

Rehashing selected RTL, SDK and runtime-source inventories gave:

| Accepted run | Files checked | Differences from current source |
|---|---:|---|
| qbs-retire-projection-vcs-20261029-01 | 61 | None |
| register-guarded-q4-vcs-20261028-01 | 98 | qbs_profile_engine_int.sv retirement update |
| prefill-production-q4-vcs-20261028-01 | 97 | Same retirement update |
| prefill-production-q8-vcs-20261028-01 | 97 | Same retirement update |

These counts are filtered source inventories, not full pin counts or coverage.
The old accepted workers are historical results, not tests on the new RTL.
The new completed pointer experiments also execute the unchanged production
Prefill baseline and check its real Q4/Q8 outputs on current RTL, for eight
queries and two groups. They do not directly rerun Register-PV Decode.

Retirement's ordinary three-way Attention regression is documented in
`qbs_retirement_acceptance_20261029.md`, but its scope must be checked against
the exact Register-PV entry before closing the remaining current-RTL gate.

## Remaining closing work

1. Determine whether an existing current-RTL regression covers the retained
   Register-PV entry. If not, run one unchanged representative native ELF with
   an explicit old-software/new-RTL admission and the original numerical and
   protocol checks. Do not waive the source difference or relabel an old run.
2. Finish the integration/reproducibility inventory of retained changes,
   including the external llama.cpp checkout's uncommitted modifications.
   Do not reset or broadly commit other work in that checkout.
3. Audit E1–E8 and close only when the remaining evidence is sufficient.

No new optimization or PPA work is part of these remaining gates.
