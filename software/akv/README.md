# AKV Runtime

`software/akv` is the framework-neutral software boundary for the Attention/KV
streaming context. It provides backward-compatible v1/v2 capability decoding,
strict D128/GQA6 problem validation, descriptor construction, overlap checks,
a callback-based blocking v1 execution API, and a functional AKV-v2 token-axis
context model.

`akv_attention_plan_create()` performs the complete capability, shape, layout,
range, and alias validation. A successful plan is immutable. Native callers use
`akv_attention_execute_native()` to avoid repeating those checks in the hot
path; the callback API remains available for reference models and emulators.

The runtime does not probe an unknown processor. A platform must establish AKV
support through a trap-safe mechanism before it calls `akv_native_info()`.
Unsupported shapes and layouts must use the caller's ordinary RVV path.

The current native kernel accepts six F16 query rows, F16 K/V rows, one F16 mask
value per active KV token, and produces six F32 D128 output rows. It keeps the
attention arithmetic in ordinary RVV; AKV commands only move Q/K/V payloads.
Callers must serialize native use because version 1 exposes one hidden context.

AKV-v2 adds a 64-token row/column-view contract without changing the v1
descriptor or instruction encodings. `akv_v2_reference_*()` defines FULL,
REFILL, row-load, K-column-load, tail, validation, and release semantics. The
generic `akv_attention_plan_create()` and `akv_attention_execute_native()` path
remains version 1 for source compatibility. A caller that has already selected
the token-axis profile uses `akv_attention_plan_create_v2()` followed by
`akv_attention_execute_v2_native()` and supplies the explicit workspace needed
by the six-row schedule. The llama.cpp/GGML RISC-V backend uses this path only
after strict Decode D128/GQA6 capability, shape, layout, mask, and worker checks;
D64, other GQA ratios, arbitrary strides, or unsupported states retain the
ordinary RVV fallback. A v2 capability bit alone therefore never changes an
otherwise unsupported call.

Run the host contract tests with:

```bash
make -C software/akv clean check
```

The CMake target automatically includes the native RVV assembly kernel for a
RISC-V target. Set `AKV_BUILD_NATIVE_KERNEL=OFF` for a contract-only build.
