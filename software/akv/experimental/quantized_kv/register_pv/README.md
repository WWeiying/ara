# Register-resident Q8_0 Decode PV

This opt-in runtime keeps decoded values in RVV registers for the online
softmax weighted update. It uses existing RVV arithmetic and QBS QK commands;
it introduces no instruction or RTL change.

## Integration

The llama.cpp adapter is in `ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp`.
Configure `GGML_RISCV_AKV_REGISTER_PV=ON` along with QBS, AKV and quantized KV
support. At execution, set `GGML_RISCV_AKV_REGISTER_PV=1` to select this path.
Both switches default to disabled. Selecting the older `GROUPED_PV` experiment
at the same time returns fallback before commands/output. Prefill selection
is unchanged and does not use this Decode implementation.

The enclosing mapper and shared selector retain type, layout, backing-memory,
alias, finite-value and workspace checks. Actual VLEN=1024, RNE and vstart=0
are checked before work. Supported inputs use Q4_0 or Q8_0 keys and Q8_0 values,
with the shared runtime's dimension and grouping limits. Failure after work
starts is terminal, not permission to retry over partially modified state.

Build with `-fno-fast-math -ffp-contract=fast`, matching production callbacks.
Use the original runtime for other capabilities. Caller-owned immutable input
and exclusive output/workspace ownership remain required.

## Evidence

- Frozen experimental implementation: `verification/akv/quantized_kv/register_pv`.
  It is retained for the completed RTL receipts. `test_promotion.py` checks that
  the promoted arithmetic/runtime differs only in local include paths and a
  comment. Future production work belongs here, not in those frozen fixtures.
- Shared runtime functional test: `register-shared-runtime-reference-20261028-01`
  under `verification/out`; 288 cases pass, plus VLEN=256 no-effects rejection.
- Library builds: `register-pv-ggml-build-20261028-01`; Prefill OFF and ON both
  build with Register-PV enabled. Compiler dependency audits find no reference
  to verification implementation sources in the production translation units.
- RTL performance acceptance is documented in
  `hardware/docs/register_pv_multishape_acceptance_20261028.md`.
- Model OFF/ON regression is launched separately as
  `register-pv-qwen3-model-20261028-01`. Its result must be read before claiming
  model acceptance. It compares all logits, selected tokens and CSR state,
  and requires trace evidence that both formats actually use Register-PV.

QEMU tests establish functional behavior, not RTL performance. These local
optimizations do not by themselves establish an end-to-end model speedup.
