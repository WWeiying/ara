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
