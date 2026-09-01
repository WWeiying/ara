# AKV Runtime

`software/akv` is the framework-neutral software boundary for the Attention/KV
streaming context. It provides backward-compatible v1/v2 capability decoding,
descriptor construction, overlap checks, a callback-based blocking v1
execution API, and a functional AKV-v2 token-axis context model. Version 2
accepts one through eight Query rows and production head dimensions 64, 96,
and 128; D96 uses a bounded D-axis tail in the unchanged D128 physical slot.

`akv_attention_plan_create()` performs the complete capability, shape, layout,
range, and alias validation. A successful plan is immutable. Native callers use
`akv_attention_execute_native()` to avoid repeating those checks in the hot
path; the callback API remains available for reference models and emulators.

The runtime does not probe an unknown processor. A platform must establish AKV
support through a trap-safe mechanism before it calls `akv_native_info()`.
Unsupported shapes and layouts must use the caller's ordinary RVV path.

The original version-1 kernel accepts six F16 Query rows, F16 K/V rows, one F16
mask value per active KV token, and produces six F32 D128 output rows. Version
2 generalizes the Query group to `q_rows=1..8` and D64/D96/D128. Its
D128/six-row arithmetic schedule remains specialized assembly; the other
admitted shapes use generic RVV arithmetic over the same token-axis context.
AKV commands move and expose Q/K/V payloads while the arithmetic remains
ordinary RVV. Callers must serialize native use because the processor exposes
one hidden AKV context.

AKV-v2 adds a 64-token row/column-view contract without changing the v1
descriptor or instruction encodings. `akv_v2_reference_*()` defines FULL,
REFILL, row-load, K-column-load, tail, validation, and release semantics. The
generic `akv_attention_plan_create()` and `akv_attention_execute_native()` path
remains version 1 for source compatibility. A caller that has already selected
the token-axis profile uses `akv_attention_plan_create_v2()` followed by
`akv_attention_execute_v2_native()` and supplies the explicit workspace needed
by the selected Query group. The llama.cpp/GGML RISC-V backend uses this path
only after Decode, capability, D64/D96/D128, `q_rows=1..8`, layout, mask, and
worker checks all pass. Arbitrary strides and unsupported states retain the
ordinary RVV fallback. A v2 capability bit alone therefore never changes an
otherwise unsupported call.

The shared runtime and directed RTL tests also define a segmented D256 contract
using two D128 physical phases without increasing K/V context capacity. This
contract is functional evidence, not a production-selector promise: the real
Gemma D256 leaf measured 47,191 cycles versus 36,043 for the strong tiled-RVV
baseline. The llama.cpp selector therefore deliberately leaves D256 on ordinary
RVV until a later implementation meets the performance gate.

Run the host contract tests with:

```bash
make -C software/akv clean check
```

The CMake target automatically includes the native RVV assembly kernel for a
RISC-V target. Set `AKV_BUILD_NATIVE_KERNEL=OFF` for a contract-only build.
