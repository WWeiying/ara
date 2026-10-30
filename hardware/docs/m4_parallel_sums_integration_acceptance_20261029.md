# Parallel M4 activation sums: integrated acceptance

## Implementation and selection

The existing llama.cpp packed Q8_K M4 quantizer now has an explicit
`GGML_RISCV_QBS_M4_PARALLEL_SUMS=1` selection. It requires the existing M4
preparation and packed-producer selections. Default behavior is unchanged.
Only integer group sums change; signed maximum, scale, rounding, encoded bytes,
layout and fallback remain the existing implementation.

Producer tags distinguish unpacked preparation (1), existing packed preparation
(2) and packed parallel sums (3). Activation cache keys include this tag;
the existing graph/source lifetime and exact-byte identity checks remain.
This avoids silently reusing output associated with a different producer.

The actual external implementation is in `arch/riscv/q8_K-m4-packed.h` and
`q8_K-m4-group-sums.h`. Its isolated tracked integration delta is
`verification/qbs/m4_group_sums/integration/llama-parallel-sums.patch`.
The external llama.cpp worktree has other pre-existing changes; they were not
committed with this delta. The patch passed a reverse application check.

## Accepted performance scope

| Paired RTL experiment | Current | Candidate | Speedup |
| --- | ---: | ---: | ---: |
| Complete M4 activation preparation | 76060 | 44443 | 1.711406x |
| Complete Q/V/K projection with reuse in both paths | 582799.5 | 550864 | 1.057973x |

Cycles are paired means, not whole-model latency. The full projection's
preparation interval falls from 97447.5 to 65924.5 mean cycles, while the QBS
execution interval stays approximately unchanged. Thus the measured full-slice
benefit is 5.48%, not 71%. Do not multiply these two ratios or combine them
with unrelated Attention ratios into an end-to-end model claim.

All these measurements use the existing RTL image. This optimization improves
software use of its vector arithmetic, slide/gather and strided-store paths;
it does not add hardware or an ISA extension.

## Integrated functional gates

The installed quantizer passes 57 complete-output comparisons at each of
VLEN256 and VLEN1024, including real model activations. Its default path,
explicit parallel path and isolated measured candidate match in all packed
bytes, FCSR/VCSR and guards. Scalar leaf oracles separately cover signed
group-sum extremes and interleaved writes.

Final model campaign:
`verification/out/m4-sums-models-20261029-01` is PASS, including rebuilt
libraries and both model stages. Register-PV Decode and grouped Prefill remain
enabled identically in both modes; only the M4 group-sum selection changes.

| Model, Q4_K_M weights | Prompt | Producer calculations OFF / ON | Paired logits |
| --- | --- | ---: | ---: |
| Qwen2.5-1.5B | 4 tokens | 220 / 220 | 911616 |
| Qwen3-1.7B | Cross-tile prompt, 33..64-token test bound | 2532 / 2532 | 911616 |

Both models use separate Q8_0 and Q4_0 K-cache runs with Q8_0 V and three
inference steps per format. All 1823232 logits are bit-exact, selected tokens
and FCSR/VCSR match, and all six comparisons per model pass. Trace acceptance
requires tag 2 on OFF and tag 3 on ON and actual RVV computations in each;
cache hits alone cannot satisfy execution coverage. These QEMU results prove
functionality, not hardware end-to-end throughput.

An independent replay checked stage receipt hashes, reran both log checkers,
and verified 988 unique sealed inputs. Pipeline SHA256:
`401c6844589ab31cca85d6ea0f53d02be68a8144b198169a251b4d2afff33d34`.

| Model | Executable SHA256 | Log SHA256 |
| --- | --- | --- |
| Qwen2.5 | `d2d3d726e810211c136dece65d5a1cbbb3084c358eb6408755d769f4769862e9` | `a0ce4b10d8b479ab874f6bb0775565705319b5d73dbf156b103a8e5152596f55` |
| Qwen3 | `42ffbdfd8b2e305f187ed9f6578e2b0581d552df9eae0c149552a562955ddee0` | `7c827b74f9c4fc7868becc676b813867034b9b51381927c001f81c78d49d0561` |

## Decision

Keep the integrated path available through explicit selection, with default
and fallback preserved. The installed source and model evidence now close the
software-promotion gate. Wider shapes, additional models and end-to-end RTL
performance are not established by these tests. The next optimization decision
must use the remaining measured bottleneck, not repeat this preparation gain
as a new hardware gain.
