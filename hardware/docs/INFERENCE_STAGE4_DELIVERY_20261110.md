# Stage4 Delivery Contract

Status: NOT COMPLETE. Attention functional terminal acceptance and its final
independent review remain pending. This document does not authorize default
promotion, Stage5 execution, synthesis or a new board campaign.

## Version And Scope

Worktree/branch: `/home/wangwy/openproject/ara_dsa`, `ara_dsa`.
Starting baseline: `d3d92ad72a3cabb91e8c333186160ae422f0866b`, tag
`stage3-resident-attention-20261110`.

| Implementation checkpoint | Commit |
|---|---|
| Retained-maxima M4 helper and directed checks | `4018b98a3` |
| Versioned feature-bearing resident Decode entry | `f50092f2d` |
| Complete projection SDK-chain firmware/checker/runner | `c475d9a88` |
| Independent ordered feature oracle and target-library probes | `62dada047` |
| Complete Attention firmware/checker/runner | `11baa67c7` |

Stage4 changes software and validation only. It reuses accepted Stage3 BUILD02
without changing RTL, bus width, SRAM capacity or arithmetic arrays. That image
retains the registered CPU overlay from Stage3; it is not a Stage4 hardware
modification. Ordinary RVV and existing runtime defaults are not replaced.
No unchecked live llama.cpp source or dirty AKV assembly is a build input.

## Measured Results And Disposition

| Pair | Strong baseline mean cycles | Candidate mean cycles | Speedup | Decision |
|---|---:|---:|---:|---|
| Real Q/V/K complete projection SDK chain | 542821 | 532106 | 1.020137x | Correct experimental helper; reject GGML/default performance promotion |
| Feature-bearing complete Attention SDK call | 67761.5 | 65152 | 1.040052x | Performance pair passes; below promotion screen; capability retention awaits functional acceptance |

Both use equal-work ABBA against the strongest applicable existing software
path. The projection includes cache/preparation/admission/native execution;
Attention includes preflight, score transforms, softmax, normalization and final
drain. Neither measures GGML graph overhead, model loading or model inference.
The approximately5% complete-call promotion screen is unchanged. Preparation's
1.172629x ratio is not a projection/model speedup. Old Stage2/3 gains are not
added to these results.

The feature parameters on the captured Qwen3 D128/H2/T137 tensor are explicit
derived controls. They are not a newly captured model workload. Other directed
dimensions, tails and grouped heads are derived fixtures, not additional models.

## Applicability And Preservation

- M4 helper: bounded K<=6144, existing packed parallel-sums producer and
  original numerical/fallback semantics. No new GGML selector is installed.
- Feature entry: explicit version2 policy, F16 Decode, one query token,
  head rows and supported D64/D96/D128 geometry. It does not reinterpret
  multi-query Prefill rows as Decode heads or accept quantized KV as F16.
- Admission requires validated availability, platform and whole-call ownership,
  supported vector/rounding state and no refill overlap. Post-start failures
  remain terminal, not partial-computation fallback retries.
- Default-OFF and Stage3-enabled/new-feature-OFF objects are unchanged.
  The actual nonzero-VSTART entry rejects before snapshots or vector work.
  Non-RNE functional acceptance requires same-FRM fallback, not an RNE oracle.
- Replay, N64, long-K, direct M8 and quantized Prefill additions were screened
  or deferred with workload-specific reasons in the evidence ledger. There is
  no automatic context growth, added third activation bank or new ISA here.
- Existing multi-query/quantized paths remain inherited support. Their presence
  is not a claim of new Stage4 coverage or performance.

## Evidence And Remaining Gate

Authoritative ledger:
`verification/performance/next_mechanism/stage4/RESULTS.md`.
Receipts reside under the sole signoff worktree:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.

| Gate | Receipt directory | State |
|---|---|---|
| A directed host/GNU/Spike | `stage4_m4_preflight_20261110_04` | PASS |
| A complete SDK-chain RTL | `stage4_projection_chain_vcs_20261110_01` | PASS; independently reviewed |
| B entry/default compatibility | `stage4_resident_features_host_20261110_06` | PASS; independently reviewed |
| B target libm/ordered oracle | `stage4_resident_features_target_20261110_02` | Oracle/probes PASS; independently reviewed |
| B complete-call performance RTL | `stage4_resident_features_vcs_perf_20261110_01` | PASS; independently reviewed |
| B complete-call functional RTL | `stage4_resident_features_vcs_functional_20261110_01` | Pending terminal acceptance |

Closing Stage4 requires the last gate's outputs, flags, guards, real route/work,
protocol and input identities to pass, plus independent review and final
disposition/committed delivery. A's below-screen decision creates no conditional
GGML integration requirement. Do not mark this contract complete from build,
scalar-probe or performance-only results.

## Stage5 Boundary

Actual GGML resident-route selection, representative whole-model/format/context
regression and unified runtime deployment remain Stage5. Any future integration
must retain explicit capability/shape/type selection, ordinary RVV fallback,
single-worker ownership and the numerical contracts. Stage4 does not default-
enable either candidate or establish new FPGA/PPA/model acceptance.
