# Actual GGML Strided Quantized-KV Graph Gate

Build-only preparation; the parent owns execution, source/model pins and strict
trace acceptance. A fixture PASS without the native traces is not acceptance.
No QEMU timing is a performance result. This is not whole-model execution.

## Inputs And Layout

Use the same `/q8` and `/q4` capture files as `ggml_live`: Q F32 D128/12 heads,
K Q8_0 or Q4_0, V Q8_0, two KV heads, capacity256, 128 visible tokens, and
`kqv_out-0.bin` containing1536 F32 outputs. The parent must pin these files and
their source provenance; this fixture verifies exact sizes and the original
zero-prefix128/negative-infinity suffix mask.

For each format, test contiguous `[128,256,2,1]` K/V and physical token-major
`[128,2,256,1]` K/V with `ggml_permute(...,0,2,1,3)` views. Every captured row,
including the masked capacity tail, is copied by byte coordinates and verified
through the resulting view. There is no `ggml_cont` or normalized K input at
dispatch. Token-major K strides are272/136 for Q8_0 and144/72 for Q4_0;
token-major V strides are272/136. Both layouts use identical logical operands.
The token-major layout is a byte permutation of the capture, not a claim that
the original capture was stored in that layout.

Each layout runs prefixes128 then5. Each prefix has an unmarked ordinary
baseline with quantized opt-in disabled, followed by two marked native runs.
All1536 outputs must be finite and meet `0.004 + 0.002 * abs(reference)` against
the ordinary baseline. Only prefix128 also uses the captured golden; prefix5
is a real-derived mask test with an ordinary-GGML oracle, not the128-token
golden. Native repeats are bit-exact. Baseline/native FCSR and VCSR must agree:
each compute starts with FCSR0/VCSR5 and snapshots both before any numerical
checks. No fixed final VCSR is guessed. For the two-thread fallback, the CSR
comparison covers the calling thread, not an aggregate of worker-thread flags.

After both layouts' native runs for a format, token-major alone runs:

1. `mask_fallback`: original128 prefix with token63 changed to negative infinity.
2. `thread_fallback`: original128 prefix, two threads.
3. `memory_fallback`: original128 prefix, one thread, normal-memory opt-in off.

Each has its own unmarked ordinary baseline under the same mask/thread/memory
settings. Fallback output must be bit-exact to that baseline and CSR must match.
The hole case does not use the unmodified captured golden. Output is poisoned
with NaNs before every baseline/native/fallback compute. After every compute,
backing bytes/digests, view metadata and all logical K/V rows are checked;
the active mask is checked separately and restored to the original at the end.

## Exact Protocol

Order: kind `q8_0,q4_0`; layout `contiguous,token_major`; visible `128,5`;
repeat `0,1`. Baselines emit no `QUANT_STRIDED_BEGIN/END` records.

```text
QUANT_STRIDED_BEGIN kind=%s layout=%s mode=native visible=%u repeat=%u
QUANT_STRIDED_END kind=%s layout=%s mode=native visible=%u repeat=%u flags=%lu vcsr=%lu max_abs=%.9g
```

`flags` is FCSR. `max_abs` is error against captured golden for128, against the
ordinary baseline for5; both comparisons are performed for128 regardless.
After all eight native calls for each kind, emit the following for the three
fallback modes above, in order (no visible/repeat fields):

```text
QUANT_STRIDED_BEGIN kind=%s layout=token_major mode=%s
QUANT_STRIDED_END kind=%s layout=token_major mode=%s exact=1
QUANT_STRIDED_PROFILE_PASS kind=%s outputs=1536 native_calls=8 fallback_cases=3 inputs_unchanged=1
QUANT_STRIDED_SUITE_PASS profiles=2 layouts=2 native_calls=16 fallback_cases=6 executor=native_qbs performance=not_measured
```

There are16 native and6 fallback intervals, plus14 unmarked ordinary baseline
computes:36 graph executions. Any `QUANT_STRIDED_FAIL` or nonzero guest exit
rejects the run. The parent must enforce complete ordering/counts and both
production trace families, not infer native dispatch from fixture PASS.

## Required Native Trace Evidence

Every native call requires `status=0 mapping=0 memory=1 runtime_called=1`,
`groups=2 executor_status=0`, plus the matching layout trace:

| Visible | QBS commands | V decodes | Token-major panels | Q8 K bytes | Q4 K bytes |
| --- | --- | --- | --- | --- | --- |
|128|16|256|8|34816|18432|
|5|4|10|2|1360|720|

Contiguous calls have the same commands/V decodes, but zero panels/key bytes.
Expected current workspace is13120 bytes for both layouts. The actual layout
trace must report the K strides above (contiguous136/34816 or72/18432), not
normalized token-major strides. Across all16 native calls:160 QBS commands,
2128 V decodes,40 gathered panels,110656 copied K bytes. These byte counters
describe software panel copies, not measured external-memory transactions.

Mask fallback must show selector MASK (`selection=6`) with zero commands,
groups, V decodes and gathered panels/bytes. Thread and memory rejection occurs
at the adapter's early admission boundary; the parent checker must follow that
frozen trace contract and require no successful native work in those intervals.
Neither fallback nor a missing layout trace may count as a native success.

## Build

Target: `ggml-quant-kv-strided`. The CMake project follows `ggml_live`, with a
new private build directory and the frozen strided integration sources supplied
through `LLAMA_SOURCE_DIR` when using the parent's snapshot. It does not reuse
old scalar-only integration archives or change their source trees.

```sh
cmake -S verification/akv/quantized_kv/ggml_strided -B <fresh-build> \
  -DCMAKE_TOOLCHAIN_FILE=/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXE_LINKER_FLAGS=-static \
  -DLLAMA_SOURCE_DIR=<frozen-private-source>
cmake --build <fresh-build> --target ggml-quant-kv-strided -j4
```

GNU C/C++, no ZCC. Fixture flags include `-Wall -Wextra -Werror -fno-fast-math
-ffp-contract=off`; normal production libraries retain their own build policy.
Build and QEMU execution have not been performed as part of this preparation.
