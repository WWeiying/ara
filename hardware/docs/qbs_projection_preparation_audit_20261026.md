# QBS projection preparation: combined Zvfh audit

2026-10-26; source/receipt review only. No source changes, build, simulation or
fresh timing. External paths below refer to `/home/wangwy/llama/llama.cpp/ggml/src`.

## Actual selected paths

The current accepted [model receipt](../../verification/akv/results/current-llama-model-20261026.json)
names `verification/out/quantkv-current-model-build-20261026-01`. Its
`compile_commands.json` compiles `ggml-cpu/repack.cpp` and `arch/riscv/qbs.cpp`
with QBS/AKV/quantKV defines and **last-effective `-march=rv64gcv_zfh_zvfh`**,
`-O3`, LP64D. The earlier `-march=rv64gcv` does not override that later flag.
The repack command has no explicit FP-contraction override: inspect the actual
rebuilt generic's instructions before relying on the historical fused oracle.
AKV's Zvfh requirement is explicit in `ggml-cpu/CMakeLists.txt:490-494`.

| Operation | Current source-selected behavior |
| --- | --- |
| Weight preparation | QBS support selects R4 repack traits before ordinary RVV traits (`ggml-cpu/repack.cpp:5190-5218`). R4 packing belongs to tensor repack/upload (`:4114-4124`, `:5110-5123`), not repeated activation preparation per N command. |
| M4 Q8_0 activation | `repack.cpp:365-383`: Zvfh calls existing `ggml_quantize_mat_q8_0_4x1`; the newer generic-equivalent M4 opt-in is in the other branch. Do not substitute a different quantization contract merely because its standalone timing was good. |
| M4 Q8_K activation | `repack.cpp:387-404`: QBS **and no Zvfh** is required for `GGML_RISCV_QBS_M4_PREPARE`; combined Zvfh unconditionally calls `ggml_quantize_mat_q8_K_4x1_ara_generic`. Setting the environment variable cannot enable it in this binary. |
| Default M4 versus tails | `repack.cpp:4855-4867`: each worker prepares complete four-row groups once into GGML workspace, already interleaved; remaining 1..3 rows use `from_float`. It is not row-quantize plus SDK pack on every N tile. |
| Optional M8 | `qbs.cpp:247,1211-1237`, `repack.cpp:4841-4851`: WIDE_M defaults OFF. When selected, row quantization precedes a barrier and worker-zero SDK M8 packing. That is a genuinely separate pass, but not the default M4 path. |
| AQ reuse | Context defaults ON (`qbs.cpp:242-245`); per-operation residency saves hardware rereads, not initial CPU quantization. Cross-op skips preparation only for Q8_K, **one activation row**, one worker, matching graph/source identity and eligible plans (`:864-898`, `:901-927`, `:1259-1330`). `repack.cpp:4818-4820,4853` implements the actual skip. No general M4 cross-graph activation cache exists. |

SDK byte packing is already RVV-backed (`software/qbs/src/qbs_runtime.c:423-458`),
but speeding it again would not automatically accelerate default GGML M4.
Plan creation/workspace construction still occurs in QBS GEMV/GEMM
(`qbs.cpp:1666-1682,1710-1728`); there is no measured attribution here making
allocator/planner caching a better first change. Context remains bounded by
split/gather/layout/capacity and singleton-N restrictions
(`software/qbs/src/qbs_runtime.c:699-751`). Keep those contracts intact.

## What has actually been measured

All numbers below are historical real-capture VCS comparisons, not current
combined-llama performance. Each pair has its own ELF/scope; do not combine them.

| Accepted receipt | Measured result and limit |
| --- | --- |
| [Q8_K VLA full projection](../../verification/qbs/results/q8k-full-projection-vla-20261023.json) | Real M4/N1536/K1536 Q4_K Q-projection, ABBA: generic preparation 533659 versus vector 391751 cycles; matrix 685347 versus 685172; total 1219006 versus 1076923. Preparation is 43.78% of the baseline interval; total reduction **11.66%**, 1.13193x. Includes preflight/quantization/bsums and command execution; excludes offline weight repack and full GGML/model overhead. `deployment_approved=false`. |
| [Q8_0 canonical preparation](../../verification/qbs/results/ggml-m4-canonical-soc-20261023.json) | Real M4/K896 preparation only: 416387 versus 277825 summed cycles, 33.28% reduction. Comparator was generic, **not today's Zvfh implementation**; neither projection nor combined-binary speedup is established. |
| [SDK pack twins](../../verification/qbs/results/runtime-pack-projection-twins-v2-20261023.json) | M4/N896/K896 row-quantize+pack projection: total 226244 to 211906; pack 31720 to 17388. Does not establish an extra pack pass in default GGML fused M4. |
| [AQ full projection](../../verification/qbs/results/context-projection-soc-20261023.json) | DIRECT 256975 versus context 257184, despite 102816 logical input bytes saved. CPU preparation was not removed. Lower traffic alone is not a latency result. |

[Q8_K live graph acceptance](../../verification/qbs/results/q8k-live-graphs-20261023.json)
proves 384 native QEMU GGML graphs, OFF/ON selection and numerics in its own
no-Zvfh build; its builder explicitly rejects the Zvfh ISA variant
(`verification/qbs/build_q8k_live_graphs.py:36-39`). It is not the missing
combined-Zvfh gate. The current model receipt proves functional execution with
232512 Q4_K and 66384 Q6_K native projection commands, no emulated projections;
those totals neither identify M4 preparation time nor prove a model speedup.
QEMU timing is not performance evidence.

## One recommended next candidate

**Revalidate and expose the existing Q8_K M4 preparation opt-in in combined
Zvfh builds, leaving Q8_0 selection and defaults unchanged.** This is a small
dispatch gap, not a new quantizer or hardware proposal. The actual
`arch/riscv/q8_K-m4.h:13-19` checks RVV/strict FP, not absence of Zvfh. Its
integer VLA domain preflight, strict first-signed-maximum rule, explicit biased
FMA, interleaved stores and 16-element bsums are already implemented
(`:25-57,61-116`). The SDK copy is `software/qbs/ggml/q8_K-m4.h`.

The prospective change is limited to making the cached enable/trace helpers
available with QBS and admitting Q8_K's branch under Zvfh
(`repack.cpp:347,390`). Keep exact `=1` opt-in, generic fallback for rejected
FRM/domain, and the Q8_0 Zvfh branch unchanged. No allocation/lifecycle changes.
Do not implement while current consumers pin these sources.

First falsify applicability using actual combined full-TU OFF/ON dispatch:
real captured M4 K1536 plus existing real K-quant captures, tails and multiple
workers; compare complete packed bytes/bsums/FCSR/VCSR, output gold and actual
selection traces. Preserve signed-max ties, zero and rejected-domain cases;
the single-row RVV quantizer is not the M4 byte oracle. Rebuild `repack.cpp`,
its library and final executable, recording effective flags/disassembly; an
environment change cannot update an old archive. QEMU can check functionality.

Only then measure a fresh same-ELF paired **complete projection call** on the
current RTL, with identical context/wide policy and real inputs. Include real
preparation, admission, commands and stores. If M4 is absent, fallback dominates,
or complete-call benefit disappears, stop this candidate; do not optimize its
microbenchmark further. It cannot accelerate M1 decode, wide-M row preparation
or calls whose quantization was already skipped. The 11.66% historical slice
result is motivation, not an estimate or promise for current llama/model time.

## Current Full-Projection Policy Check

The host test `verification/qbs/combined_zvfh_m4/test_plan_probe.py` executes
the current production planner using reference capability words, not a mocked
plan. It checks the M4/N1536 Q4_K projection family:

| K | Packed Q8_K bytes | Context eligible | Commands |
| ---: | ---: | --- | ---: |
| 512 | 2336 | Yes | 48 |
| 1024 | 4672 | Yes | 48 |
| 1536 | 7008 | No | 48 |

All three plans use M4/N32 commands with no split-K or activation gathering.
The byte budget is 4672. Thus the historical real M4/N1536/K1536 DIRECT
benchmark is consistent with the current planner's capacity restriction;
shrinking K to 1024 would change the eligible execution policy. This host
test does not establish which capability words an arbitrary RTL image returns.
The eventual VCS run must verify the chosen image contract.

The old standalone projection harness still omits GGML plan creation,
workspace allocation and scheduling. A fresh counterpart may measure the
preparation-plus-command slice, but must not call that a full GGML or model
speedup. Keep these costs distinct and use the actual graph test to verify
dispatch. Rebuild from the current shared canonical quantizer and SDK; do not
reuse an old private candidate header or combine historical cycle totals with
new preparation measurements.
