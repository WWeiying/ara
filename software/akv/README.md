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
contract is functional evidence, not a production-selector promise. The shared
D256 kernels now reuse a column/row across four Query heads; capable devices
also use the existing four-column command. Incomplete head groups retain the
single-head loop, and each output element retains its previous F32/F16 rounding
order. No RTL capacity or encoding changes are required.

On the same current simulator, real Gemma KV17 improved from 47,393 to 30,255
cycles, versus 35,408 for strong tiled-RVV. This is still below the 1.2x admission
gate. A real KV140 capture also exposes an existing tiled-F16 rounding-order
mismatch in both AKV and tiled-RVV. The llama.cpp selector therefore continues
to leave D256 on ordinary RVV. See
[D256 evidence and numerical boundary](../../hardware/docs/akv_d256_efficiency.md);
neither a faster failing result nor a host-only test admits a production path.

Run the host contract tests with:

```bash
make -C software/akv clean check
```

The CMake target automatically includes the native RVV assembly kernel for a
RISC-V target. Set `AKV_BUILD_NATIVE_KERNEL=OFF` for a contract-only build.

## Batched Decode and Layouts

`akv/akv_decode.h` accepts Q/output `[batch, query_head, D]`, K/V
`[batch, kv_head, token, D]`, explicit byte strides and all buffer capacities.
D is contiguous. K/V head/token axes can be exchanged and rows padded; only
the mask can broadcast across batches using a zero batch stride. This is not
a paged-KV interface.

`akv_decode_validate` checks every group, span, capability and cross-group
output/input overlap before issue. `akv_decode_execute` traverses groups
serially and supplies immutable plans to the caller's executor callback.
Large GQA is split within each KV head at the device's maximum Query-row count:
GQA17 becomes 8+8+1, not a larger hardware context. The callback receives the
batch and first logical Query head for selecting the corresponding metadata.

Callers serialize the entire operation against other users of the context.
The completion count reports successful groups. An execution failure may
already have written output and must not trigger transparent fallback.

Logical D values are 64/96/128/256 and KV length is 1..65535; device and
production-policy restrictions still apply. D256 remains outside the GGML
selector. Batch support here does not mean GGML admits batch>1: its selector
still rejects that case.

## Optional Attention Features

`akv/akv_features.h` defines optional Decode score processing using software
and ordinary RVV, without new RTL commands or storage:

1. scale the QK dot product;
2. optionally apply `softcap * tanh(score / softcap)`;
3. optionally add a per-head relative-position slope;
4. add the F16 mask, optionally multiplied by a positive per-head scale;
5. exclude masked/window-outside positions and run online Softmax/PV.

An optional per-head sink adds one score to the denominator and zero Value.
Window bounds and relative positions use absolute token positions. Q/K/V must
be finite and masks finite or negative infinity. The F32 oracle rejects invalid
masks before writing output; native callers must validate that data contract
before issue. A leading completely masked tile now produces zero weights,
avoiding `-Inf - -Inf`. An entirely masked row without a sink returns zero.

`akv_attention_execute_v2_with_features_native` uses the existing context and
RVV schedule. `akv_attention_execute_v2_native` remains the NULL-feature call.
When every feature is disabled and every active mask value is zero, the shared
helper uses that original vector score path after validation. It does not
discard mask holes, finite additive bias, windows or sinks. ALiBi coefficients
are computed only when mask scaling is enabled.
`...with_features_reference` is a mathematical F32 oracle, not a bit-exact
native model: native Value accumulation rounds to F16 and uses the existing
RVV exp approximation. Compile the oracle without fast-math and compare with
an explicit tolerance.

The private GGML adapter admits larger GQA, finite masks with holes, ALiBi
mask scaling, softcap and sinks only with `GGML_RISCV_AKV_PORTABLE=1`.
GGML's ALiBi convention scales its constructed mask; do not also add an
independent positional bias. Prefill selection is not broadened. New optional
paths have functional tests but no general performance guarantee; leave the
flag off until the real model/shape passes the performance gate.

GGML's QEMU functional executor retains its F16 Value accumulator for both
plain and feature-enabled Decode. The standalone F32 oracle is not used as a
drop-in replacement for that numerical schedule. Neither executor predicts
the native token-tiled reduction/exp rounding bit for bit; real captured leaves
are checked separately on VCS.

Worker-zero calls from different GGML graphs use a process-local mutex around
the complete context lifetime. This is not OS context save/restore or
cross-process isolation. The native platform must prevent uncoordinated users
or migration during the lifetime; OS ownership is required for multi-process
deployment.

## Portability Verification

- `make -C software/akv check`: existing contract plus 192 combinations of
  batches, GQA, D, KV tails and head/token-major layouts, plus feature/error tests.
- `bash verification/akv/run_ggml_portability_test.sh`: cross-built GGML against
  its original CPU Attention on RVV QEMU, using the **AKV software oracle**;
  18 combinations, two concurrent graphs, fallback and default-path checks.
- `bash verification/akv/run_portability_rtl.sh`: fresh isolated VCS image,
  native feature smoke followed by QBS/AKV/ordinary-RVV handoff. Launch long
  runs in tmux instead of polling continuously.
- `verification/akv/run_portability_stage2.py`: pinned model preparation,
  isolated QEMU model checks and same-capture RVV/original-AKV/portable-AKV
  VCS tests. Each VCS run is limited to three hours, without overwriting an
  earlier cohort. `summarize_portability_stage2.py` collects all raw counters
  and model fallback reasons; see the work document for commands and results.

CMake consumers can use `akv::runtime` through add-subdirectory or the
installed `find_package(akv_runtime CONFIG REQUIRED)` package.
See `hardware/docs/qbs_akv_portability_work.md` for scope and evidence.
