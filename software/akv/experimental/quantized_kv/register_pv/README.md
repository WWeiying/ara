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

Compile `entry.c`, not `runtime.c` separately. The public entry samples actual
CSRs before report initialization can call a vectorized libc routine. It
includes the internal runtime under a private entry name. This is the
same early-guard implementation accepted in the independent RTL pair.

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
- Guarded-entry functional tests: `register-early-entry-runtime-20261028-01`
  and `register-early-entry-guards-20261028-01` under `verification/out`;
  288 normal cases and 58 CSR/capability rejection cases pass.
- Final libraries and models: `register-pv-final-models-20261028-01` is PASS.
  Prefill OFF and ON libraries build with Register-PV support; dependency
  audits find no verification implementation sources in production units.
  Qwen2.5-1.5B and Qwen3-1.7B OFF/ON tests compare 1823232 logits bit-exactly,
  with identical selected tokens and CSR state. Each model exercises both K
  formats, with 112 Register-PV-enabled Decode completions in its ON mode.
- Independent final replay rechecked 985 unique inputs and all three stage
  receipts. See `hardware/docs/register_pv_guarded_acceptance_20261028.md`.
- Guarded-entry RTL pair: `register-guarded-q4-vcs-20261028-01` gives 1.111664x
  full-Decode-call speedup (47885.5 versus 43075.5 mean cycles), with bit-exact
  paired outputs and independent protocol acceptance. Earlier unguarded
  multi-format/context results are not substituted for this final entry.

QEMU tests establish functional behavior, not RTL performance. These local
optimizations do not by themselves establish an end-to-end model speedup.
