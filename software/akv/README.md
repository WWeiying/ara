# AKV Runtime

`software/akv` is the framework-neutral software boundary for the version-1
Attention/KV streaming context. It provides capability decoding, strict
D128/GQA6 problem validation, descriptor construction, overlap checks, and a
callback-based blocking execution API.

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

Run the host contract tests with:

```bash
make -C software/akv clean check
```

The CMake target automatically includes the native RVV assembly kernel for a
RISC-V target. Set `AKV_BUILD_NATIVE_KERNEL=OFF` for a contract-only build.
