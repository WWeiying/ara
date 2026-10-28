# Controlled GGML Prefill dispatch integration

The two patches contain only this integration's changes relative to the saved
local llama.cpp files, not the other uncommitted QBS/AKV modifications. They are
already applied in `/home/wangwy/llama/llama.cpp`; do not apply them again there.
The before-files remain in `verification/out/prefill-integration-before-20261028-01/`.
These patches require the existing experimental quantized-KV backend.

Build options, in addition to existing RVV/QBS/AKV/quantized-KV options:

```text
GGML_RISCV_AKV_QUANT_PREFILL=ON
GGML_RISCV_AKV_PREFILL_DIR=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/prefill
```

Runtime requires all existing quantized-KV opt-ins and the additional
`GGML_RISCV_AKV_QUANT_PREFILL=1`. The CMake option defaults OFF. The explicit
source-directory option points at the reviewed experimental kernel; this is
not yet a self-contained upstream installation.

For multiple query tokens, the new dispatch invokes the checked C entry under
the existing QBS direct-run owner and outer AKV lock. It allocates a private
workspace with 64-byte alignment and releases it after synchronous completion.
Single-query Decode follows the original code. Existing type, thread, use_ref,
normal-memory and capability restrictions remain. Unsupported requests return
fallback before execution; execution failures remain terminal at the AKV caller.

The trace marker `GGML_RISCV_QUANT_PREFILL` includes status, mapping, memory,
runtime entry, selection reason, commands, completed groups, V decodes, query
quantizations, K gather bytes and workspace bytes. A trace candidate is not proof
of successful execution: require status=0 and nonzero completed work.

Validation so far: RISC-V GNU C++17 syntax check with `rv64gcv_zvfh` and both
`GGML_USE_RISCV_QUANT_KV` / `GGML_USE_RISCV_QUANT_PREFILL` enabled. Existing host
C-entry numerical tests passed separately. The initial manual syntax command
omitted the existing quantized-KV macro and therefore lacked direct-run API
declarations; repeating with the actual enabled configuration passed.

Pending: normal CMake build with the option ON/OFF, real graph dispatch execution,
enabled/disabled model comparisons, fallback regression and trace accounting.
The new frontend's heap allocation and ownership/dispatch overhead have not been
measured by the earlier C-entry RTL benchmark. Do not label that benchmark's
1.455x as integrated graph or model speedup. No RTL changes were made here.
