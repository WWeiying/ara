# RVV Value Decode In The Public Attention Entry

## Purpose And Controlled Change

The finite Q8_0 V decoder already has independently replayed native evidence
in `verification/akv/results/quantized-kv-value-decode-20261024.json`. This
successor measures its contribution inside complete Attention rather than
multiplying its isolated speedup by a previous Attention speedup.

`attention_value_rvv_main.c` includes the unchanged public-entry benchmark and
wraps only its call to `akv_quant_native_execute`. A local copy of the bindings
replaces `decode` with the accepted `akv_quant_q8_0_value` implementation. The
real shared runtime still performs admission before calling that decoder.
The wrapper never changes the caller's binding object.

The ordinary schedule continues calling the original production
`dequantize_row_q8_0`. Query quantization, QBS execution, online Softmax, PV,
normalization, output checks, CSR checks, ABBA order and timing boundaries are
unchanged. The decoder's finite-scale and 32-element-block preconditions are
provided by the existing runtime admission. No new instruction, RTL change,
scratch capacity increase or enabled GGML dispatch is involved.

Both real captures have Q8_0 V. The Q4_0/Q8_0 labels below describe **K**, not V.
Each experiment retains D128, six Query heads sharing one KV head, 128 visible
tokens, capacity256 and 768 outputs per trial. Mapping and runtime admission
remain inside the candidate timer. Actual backend allocation-query overhead is
not included; this is not a whole-model measurement.

## Build And Evidence

`build_value_rvv_attention.py` consumes an immutable checked public-entry build.
It retains the original build, ELF, object files and manifests, emits a separate
main object and ELF, and reuses the other original objects. It verifies both
decoder symbols and the vector load, extension, conversion, multiplication and
store instructions in the new decoder's disassembly. All inherited inputs and
new source dependencies are pinned. The existing numerical/protocol worker is
reused without changing its acceptance checks.

Prepared builds:

- `verification/out/akv-quantkv-value-rvv-attention-q4-build-20261024-01`
- `verification/out/akv-quantkv-value-rvv-attention-q8-build-20261024-01`

Corresponding native result directories:

- `verification/out/akv-quantkv-value-rvv-attention-q4-20261024-01`
- `verification/out/akv-quantkv-value-rvv-attention-q8-20261024-01`

Before launch, the original decoder experiment was independently replayed into
`verification/out/akv-quantkv-value-rvv-attention-decoder-audit-20261024-01`:
all eight trials, 262,144 real output words and 3,584 finite boundary outputs
passed. The public-entry checker/worker and actual GGML graph tests also passed
all nine host tests, including Clang ASan/UBSan graph checks.

Each native worker independently checks the corresponding accepted original
private Attention run, image/source identity, all four numerical records, full
output words, actual QBS work, backend/CVXIF/AXI protocol and simulator exit.
Only a terminal checked `PASS` in the new run can establish full-path benefit.
Prepared builds and a live simulator are not acceptance evidence. Do not edit
their inputs during execution or add these cycles to previously measured cycles.

## Remaining Integration

After acceptance, use the same decoder callback in the experimental GGML
adapter with explicit capability/type/shape selection. Preserve ordinary RVV
fallback and distinguish rejection before work from failure after partial work.
Real model dispatch and platform serialization remain separate required gates.
