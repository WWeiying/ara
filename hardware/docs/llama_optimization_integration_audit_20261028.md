# Current optimization integration audit

This is a source audit, not new model performance evidence. It distinguishes
implemented/opt-in paths from defaults and from experimental kernels. No
external llama.cpp files or production switches were changed by this audit.

## Actual model call paths

| Work | Current integration | Conditions / remaining gate |
|---|---|---|
| M4 Q8_K activation preparation | `repack.cpp`, shared preparation helpers | `GGML_RISCV_QBS_M4_PREPARE`; supported QBS block type and shape |
| Packed M4 producer | Shared `q8_K-m4-packed.h` | `GGML_RISCV_QBS_M4_PACKED=1`, with preparation enabled |
| Prepared activation reuse | `repack.cpp`, `q8_K-prepared-reuse.h` | `GGML_RISCV_QBS_M4_CACHE=1`; graph/lifetime policy and exact-byte cache checks |
| Quantized Decode Attention | `quant-kv.cpp` -> shared strided runtime | CMake `GGML_RISCV_AKV_QUANT_KV`, normal-memory runtime opt-in, admission |
| Quantized grouped Prefill | Same entry -> canonical Prefill C entry | Additional CMake and environment `GGML_RISCV_AKV_QUANT_PREFILL` opt-ins |
| Grouped decoded-F32 PV | Existing explicit opt-in, not default | `GGML_RISCV_AKV_GROUPED_PV`; prior regression must not be advertised as a gain |
| Q8_0 register decode/PV | Independent experiment only | No production GGML dispatch; actual RTL whole-call comparison pending |

Quantized-KV Decode and quantized Prefill CMake options default OFF. Source
presence therefore does not prove a user's binary executes those paths. Model
validation must record CMake flags, environment switches and actual execution
counters, not merely list supported code. Standard fallback remains important.

The quantized-KV entry admits Q4_0/Q8_0 K with Q8_0 query quantization and Q8_0 V.
It requires a single worker, normal-memory opt-in, capability/layout checks,
and the runtime's supported shape/mask/numerical domain. This is separate from
the existing floating-point AKV path and from QBS projection weight profiles;
it does not narrow all QBS projections to these two formats.

## Reuse is not universal

The prepared activation cache is currently restricted to Q2_K/Q3_K/Q4_K/Q5_K/
Q6_K weights with Q8_K activations, non-wide-M plans, single-worker graph
execution, suitable graph neighbors and matching source/lifetime identity.
The helper additionally bounds groups to 0--7, K to multiples of 256 up to
6144, RNE and vstart=0. It checks the producer tag and exact input bytes; it
does not assume equal pointers imply equal tensor contents. Misses retain
the producer path, and changes of graph epoch/source invalidate eligibility.

These are deliberate correctness and capacity limits. Widening them requires
evidence of useful misses in real graphs, not just increasing a constant.
The accepted QKV slice reuse gain is not a universal model-wide speedup.

## Runtime costs not in the current inner-call ROI

`quant-kv.cpp` uses a bounded 16 KiB stack workspace for Decode. Prefill
allocates an aligned workspace with malloc/free per invocation, then executes
under the QBS direct-run ownership mechanism. The standalone full-C-call ROI
includes admission/preparation/QK/PV/drain but does not include that C++
allocation, dispatch or ownership acquisition. Those costs must be included
in an eventual model-level assessment.

A persistent Prefill workspace is a possible follow-up, not an implemented
optimization. It would need explicit worker ownership, bounded allocation,
recursive-call/concurrent-graph behavior, allocation-failure fallback and
reset of per-invocation panel validity. Reusing storage must not accidentally
reuse stale K/V contents. First measure allocation/dispatch cost; do not assume
it dominates QBS or attention execution.

## Floating-point compiler contract

Current GGML runtime files are built with `-fno-fast-math -ffp-contract=fast`.
The real-data register-PV VCS pair uses this production contraction setting
for both runtime implementations. Earlier independent leaf/online tests used
`-ffp-contract=off`. Neither mode enables reassociation under fast-math, but
scalar multiply-plus-add expressions may still fuse under `fast`.

The complete runtime/reference suite must therefore be executed in both
contraction modes. The QBS descriptor reference model is an independent
arithmetic executor in that test; it is not evidence of RTL performance.
Full VCS output/flags and later GGML model regression remain separate gates.

The production-contraction repeat is now PASS:
`verification/out/register-runtime-fast-reference-20261028-01/result.json`.
All 288 runtime/reference cases and the separate VLEN=256 rejection boot
passed, with exact output/flags, unchanged panel accounting and checked
failure handling. Input hashes matched before/after. ELF SHA256:
`7aa53cd420dbdf46ee9a190f7f2fe7023c817b079f8f91bce44b19e6c3ecebe0`.
This supplements, not replaces, the earlier contraction-OFF receipt.
Reproduction: `register_pv/run_online.py --runtime --fp-contract fast
--execute-reviewed --output <fresh-output-under-verification/out>`.

## Source identity inspected

External runtime: `/home/wangwy/llama/llama.cpp`. It has uncommitted integration
changes; this audit preserved them rather than resetting or committing them.

| Source | SHA256 |
|---|---|
| `ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp` | `94a7b7a18b2c581f56835ebefe109257d0878341fab09fed50b8e76f80b8d0c4` |
| `ggml/src/ggml-cpu/repack.cpp` | `d6a52a7f085acfca9411e006ef9db1101654e636e184c67c83b74c1c9bbd1ea3` |
| `ggml/src/ggml-cpu/CMakeLists.txt` | `81d5eeb001884fb27b554b505b01f9e50e4d19507c90bf3c25e9d116b9c0c7ee` |
