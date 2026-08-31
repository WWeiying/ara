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
deliberately remains version 1 until D64, additional GQA ratios, arbitrary
strides, worker ownership, and trap-safe capability routing are closed. A v2
capability bit therefore does not silently select the experimental kernel.

Run the host contract tests with:

```bash
make -C software/akv clean check
```

The CMake target automatically includes the native RVV assembly kernel for a
RISC-V target. Set `AKV_BUILD_NATIVE_KERNEL=OFF` for a contract-only build.
