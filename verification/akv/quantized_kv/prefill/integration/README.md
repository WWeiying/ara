# Controlled GGML Prefill dispatch integration

The two patches contain only this integration's changes relative to the saved
local llama.cpp files, not the other uncommitted QBS/AKV modifications. They are
already applied in `/home/wangwy/llama/llama.cpp`; do not apply them again there.
The before-files remain in `verification/out/prefill-integration-before-20261028-01/`.
These patches require the existing experimental quantized-KV backend.

Build options, in addition to existing RVV/QBS/AKV/quantized-KV options:

```text
GGML_RISCV_AKV_QUANT_PREFILL=ON
```

Runtime requires all existing quantized-KV opt-ins and the additional
`GGML_RISCV_AKV_QUANT_PREFILL=1`. The CMake option defaults OFF. The explicit
source-directory option now defaults to
`${GGML_RISCV_AKV_RUNTIME_DIR}/experimental/quantized_kv/prefill`. No explicit
verification path is needed. The eight accepted C/H files live in software;
their old verification paths are compatibility includes only. This integration
still requires the existing QBS/AKV runtime and quantized-KV backend patches.

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

The shared algorithm has passed normal CMake OFF/ON builds, real GGML graphs,
and Qwen2.5/Qwen3 Prefill OFF/ON model comparisons with bitwise-identical logits
and matching token/CSR results. The latest selector acceptance is documented in
`hardware/docs/quantized_selector_block_max_acceptance_20261028.md`.
Directory-relocation validation is a separate gate; see
`hardware/docs/quantized_prefill_software_relocation_20261028.md`.

Frontend heap allocation and ownership/graph dispatch are outside the earlier
C-entry RTL ROI. Historical Prefill native measurements also used a scalar V
callback; see `hardware/docs/quantized_native_binding_audit_20261028.md`.
Do not label those measurements as integrated graph/model speedups. This
directory relocation changes no RTL, ISA, arithmetic or dispatch policy.
