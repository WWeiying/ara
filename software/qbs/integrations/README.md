# GGML segmented R4 integration

`llama-segmented-r4.patch` contains the reviewed local QBS software and tests
relative to llama.cpp commit `8ed9403e37f1ceb43c6279cdefef01354eac6fd3`.
It is already applied in `/home/wangwy/llama/llama.cpp`; do not apply it twice.
No unrelated AKV changes are included. On another checkout, run
`git apply --check` before applying and preserve any local modifications.

Build with `GGML_RISCV_QBS=ON`, tests enabled, and
`GGML_RISCV_QBS_RUNTIME_DIR` pointing to this worktree's `software/qbs`.
Rebuild the runtime and consumers together because the plan structure changed.

The weight policy `GGML_RISCV_QBS_SEGMENT_K_BLOCKS` is frozen on first use.
Zero/unset retains the original layout; nonzero opts into segment-major R4.
It must be set before loading model weights. Hardware instructions and ABI
descriptors do not change. Default production selection is unchanged.

See `hardware/docs/qbs_segmented_r4.md` for data layout, numerical boundaries,
graph evidence, native evidence and outstanding acceptance gates. The graph
runner is `verification/qbs/run_ggml_segmented.py`; use a new evidence directory
for each run. QEMU emulation here is a software integration test, not RTL
performance evidence.

Use `--suite natural` to check 280-block Q4_K/Q8_0 GGML matrices under the
unchanged 256-block device limit. It checks three layout/mode policies and
rejects missing K tails, lost command work, layout drift, and changed output
digests. The default `--suite full` retains the nine-profile short/forced-split
matrix and expert graph suite. For example:

```bash
python3 verification/qbs/run_ggml_segmented.py \
  --binary /home/wangwy/llama/llama.cpp/build-rv64-qbs-segmented-20261023/bin/test-ara-q4k-repack \
  --out verification/out/qbs-natural-new-run --suite natural
```

The natural-K matrix oracle follows the selected GGML activation quantizer,
then independently dequantizes and calculates in FP64. It does not claim
bit-identical reference/optimized quantization: compiler FMA contraction can
change boundary cases. The source, ELF, runtime and tools are hashed per run.

`--suite context` executes 48 native-QBS GGML graph cases; `--suite barrier`
executes eight projection/MoE/projection cases. Both require `--native-qemu`
pointing to an isolated QBS-enabled system emulator. First run
`verification/qbs/qemu/attest_native_build.py --build /path/to/qemu-build`
to incrementally build and create its new-only `native-model-manifest.json`.
The runner rejects a stale executable, changed source/configuration or a build
configured against a different source tree. These are functional instruction
tests, not RTL performance measurements.

The patch includes a scoped context-ownership fix: lookahead does not reserve
across expert matmuls or identity-ineligible ordinary matmuls. It keeps adjacent
compatible projection reuse. The reproduced self-wait, fixed tests and remaining
in-place/alias safety gate are described in `qbs_segmented_r4.md`.

## Pending float-gap context refinement

`llama-float-gap-context.patch` is a separate, **not yet installed** candidate
on top of the current local runtime. It is not a replacement for the segmented
patch above. It permits lookahead across ordinary F32/F16-weight matrix
operations only after the existing write/alias guard passes and only while
those weights have no QBS profile. Expert and incompatible quantized matrix
barriers remain unchanged. No descriptor ABI, hardware resource or public
runtime option changes.

The patch reproduces the private candidate exactly; the model-test-only
`GGML_QBS_FLOAT_GAP_TEST` switch is deliberately absent. Existing cross-op
context opt-in, capability/shape selection and ordinary RVV fallback remain.
`test_float_gap_patch.py` checks application, exact equivalence to the tested
candidate, rejection of double application, reversal and preservation of the
runtime checkout. It performs these operations only in a temporary directory.

The model pair and 16 executed graph cases are documented in
`hardware/docs/q8k_float_gap_model_pair_20261026.md`. The captured mixed-profile
Q/V/K RTL performance experiment is pending. Do not install the candidate into
a checkout pinned by an active worker. After its performance gate, apply only
after `git apply --check`, rebuild the production runtime, and repeat affected
graph/model gates using that actual build. Private candidate results alone
do not establish acceptance of a newly rebuilt production binary.
