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
