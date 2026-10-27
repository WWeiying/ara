# Cross-projection context reuse: paired model acceptance

## What changed

The private runtime candidate permits context lookahead across an intermediate
F32/F16-weight, F32-activation matrix operation that has no QBS weight profile.
The existing input-write/alias guard runs first. Expert operations, unknown
operations, incompatible quantized consumers and input overwrites remain
barriers. No hardware capacity or RTL is changed.

In the captured graph, intermediate floating-point Hadamard transformations
previously stopped lookahead between Q, V and K projections despite not using
the QBS context. This is not permission to skip all unsupported operators or
to reuse data based only on pointer equality.

## Direct old/new comparison

Evidence directory:
`verification/out/q8k-float-gap-pair-20261026-01`.

The same executable selects the old and candidate policies. M4 preparation
remains enabled in both; other runtime options are fixed. The test uses
Qwen2.5-1.5B Q4_K_M, two KV-cache configurations, a four-token prefill and two
Decode steps per configuration. QEMU supplies functional execution, not
hardware performance measurements.

| Observation | Old policy | Candidate policy |
| --- | ---: | ---: |
| Activation quantization calls | 1068 | 844 |
| Quantizations skipped through context reuse | 114 | 338 |
| Quantized bytes produced | 6694392 | 6301944 |
| Context fills | 568 | 344 |
| Context releases | 568 | 344 |
| Context reuse events | 103736 | 104184 |
| Remaining exact-byte duplicate preparations | 390 | 166 |

All six comparisons passed: 911616 logits were bitwise equal, with equal
tokens and FCSR/VCSR. Native command counts and matrix work were equal after
excluding only the deliberately changed context counters. Fill and release
counts balance independently in each mode. The 224 saved calls reconcile
exactly with the increase in skipped quantizations. Produced bytes decrease
by 392448; this is preparation output volume, not measured DRAM traffic.

The log SHA256 is
`f160270541680ce60f2653627c9324233f0cb87356b5222f4a649301d43a61b1`.
The runner checks its sealed input hashes before reporting success.

## Interpretation and remaining acceptance gates

This closes the direct old/new model functional comparison, unlike the earlier
candidate-only M4 OFF/ON comparison. It does not establish a whole-model
speedup, prove all graph alias combinations, or cover all model families.
The remaining 166 duplicate preparations are four-row cases outside the
current single-row hardware-context policy; removing that restriction alone
would exceed capacity for the measured shape.

Before production integration:

1. Exercise actual GGML graphs with intervening float matrices, input aliases,
   incompatible quantized consumers, expert/custom barriers and graph changes.
   The existing 17-fixture extracted-control test is complementary, not a
   replacement for runtime execution of those graphs.
2. Measure paired projection consumers using real model data on VCS, including
   quantization, context fill/reuse/release, intervening work and output stores.
   Keep arithmetic workload and numerical checks identical.
3. Integrate the reviewed policy into the production backend and rerun the
   affected runtime tests with fallback and capability selection preserved.

The candidate is not yet installed in the production runtime. A separate
single-output quantizer whole-projection VCS experiment is also running; its
result must not be attributed to this cross-projection policy.

## Real GGML tensor alias checks

`verification/qbs/q8k_decode_sums/test_float_gap_ggml_alias.py` passed 16
checks using real GGML allocation/view APIs and `ggml_nbytes`. It compiles the
current GGML base sources instead of loading an older host shared library.
The production write-guard function is extracted without replacing its body.
Its C++ execution is checked with UndefinedBehaviorSanitizer.

The checks include exact overlap, partial overlap from either side, adjacent
non-overlapping buffers, a strided destination whose second row overlaps the
input, a strided input whose second row is overwritten, missing addresses,
custom/optimizer barriers and metadata-only views. All expected admissions
and rejections matched. In particular, the byte span includes stride gaps;
counting elements alone would have missed the second-row hazards.

This strengthens the alias-guard evidence, but does not execute a GGML graph
or replace the remaining graph-level ownership and fallback tests. Tensor
storage is genuinely allocated; selected operation tags and result addresses
are assigned by the fixture to model arena reuse deliberately.

## Executed paired GGML graphs

`float_gap_graph.cpp` executes real backend graphs, not extracted policy
functions. Each policy runs F32 and F16 independent matrix gaps plus an
in-place input scaling barrier, across two changed-input epochs at the same
address. QBS weights use the production repack buffer. Both projections'
outputs and FCSR/VCSR are compared bitwise across policies; independent checks
also require the gap's identity-matrix result, unchanged projection results
across safe gaps, doubled results after scaling, and changed results across
epochs.

The initial N32 case passed through DIRECT because one output tile is not
context-eligible. It is retained as fallback evidence, not reuse evidence.
The successor N64/K256 case executes two output tiles and covers reuse:

| Counter | Old | Candidate |
| --- | ---: | ---: |
| Quantizations | 12 | 8 |
| Cross-operation quantizations skipped | 0 | 4 |
| Native commands | 24 | 24 |
| Native context fill / release | 12 / 12 | 8 / 8 |
| Native context reuse | 0 | 8 |
| Cross-operation fill / reuse / release | 0 / 0 / 0 | 4 / 4 / 4 |

All 12 graph executions and the 3168-byte output/CSR pair passed. Evidence is
`verification/out/q8k-float-gap-graphs-20261026-03`. The original worker is
FAIL because its checker incorrectly required nonzero *cross-operation*
fills in the old policy. The corrected checker distinguishes these from
ordinary per-operation context fills. An independent
`corrected-checker-audit.json` records PASS without replacing the original
report; every pinned input except the explicitly corrected checker is
unchanged. Log SHA256:
`a57529df3bee233665995ac5cfd7245bc2522253db59309f90565ee5802e5d7a`.

These are bounded synthetic graph boundary tests, complementary to the real
model run above. They establish neither RTL speedup nor exhaustive expert,
custom-operation, concurrent-graph or cancellation coverage.
