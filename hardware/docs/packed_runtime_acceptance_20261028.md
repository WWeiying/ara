# Packed Preparation Runtime Acceptance

## Current Evidence

The combined software change is installed in the local llama.cpp checkout.
It reuses existing QBS hardware; no RTL changed in this integration.

| Check | Result | Scope |
| --- | --- | --- |
| Clean normal CMake build | PASS | Four normal libraries, 896 source inputs |
| Paired GGML graphs | PASS | 24 graphs, 46272 paired output/state bytes |
| Ordinary RVV strided inputs | PASS after diagnostic-schema audit | Four cases, 704 finite bit-exact outputs |
| Normal-library expanded QBS layout matrix | PASS | 65 paired cases, 4024 outputs, 344 native commands |
| Full-output Q/V/K VCS slice | PASS | 1659464 to 1166072 paired cycles, 1.4231231x |
| Packed plus cache model pairing | Running | No completion or model speedup claim yet |

All outputs are under `verification/out`, with prefixes
`m4-packed-normal-{build,graph,stride,model}-20261028-01` and
`m4-packed-normal-stride-audit-20261028-01`.
The expanded matrix is `m4-packed-normal-expanded-20261028-01`: Q4_K,
Q6_K, Q4_0 and Q8_0, M=1/3/4/7/8/15, one/two workers, row padding,
non-unit element strides and wide-M selection. Packed is explicitly enabled;
Q8_K producer records must identify tag 2 and include actual RVV execution.
Weights in this matrix are deterministic test weights and activations come
from a real capture; do not describe every matrix input as a real-model weight.

The ordinary-RVV run initially received FAIL from the older checker because
it rejected all `M4_SELECTED` records. Actual output mismatches were zero.
The successor audit requires exactly 16 records, each immediately paired with
the existing preparation record, with `source=direct`, `tag=0`, `path=generic`
and matching K. It then retains every original numerical, backing-integrity,
fallback-selection and completion check. Three negative mutations are
rejected. The original FAIL receipt and raw log remain unchanged; no simulator
rerun or numerical tolerance change was used to obtain the audit result.

## Attention Scope: Separate the Two Entrypoints

`GGML_RISCV_AKV=0` does not disable every accelerated Attention path.
In `arch/riscv/akv.cpp`, the independently selected quantized-KV entrypoint
runs before the ordinary AKV admission path. With quantized-KV and normal
memory enabled, `quant-kv.cpp` invokes `ggml_riscv_qbs_direct_run` for QK,
while value decoding and accumulation use shared software/RVV helpers.
That is not evidence that native AKV instructions executed.

The previous completed normal-library model log
`m4-prepared-installed-model-20261027-01/qemu.log` contains the following
activity **per preparation configuration**:

| Activity | Count |
| --- | ---: |
| Attention calls, two KV formats and six model steps | 168 |
| Completed quantized Decode calls | 112 |
| Prefill shape fallbacks | 56 |
| Reported native command attempts | 448 |
| Reported value decodes | 1232 |

The workload uses 28 layers, a four-token prompt and two subsequent Decode
steps, for both Q8_0/Q8_0 and Q4_0/Q8_0 KV types. Each Decode call reports
four command attempts and two completed groups. Prefill has multiple query
tokens and fails the mapper's `q->ne[1] == 1` requirement with reason 5
(`MAP_SHAPE`), before native execution. This does not imply the separate
unquantized AKV Prefill implementation is absent.

`verification/qbs/m4_prepared_reuse/check_model_attention.py` reconstructs all
28 layers for every step, checks the paired activity, and rejects altered
command counts, runtime selection and fallback reasons. The historical log
passes this audit. Apply the same audit to the new model log only after it
finishes. These counts are dispatch records, not retired-instruction proof,
time fractions, tokens/s or whole-model acceleration.

## Next Work

Finish normal-library packed/cache model pairing first, preserving the running
source inventory. The normal-library multi-format strided-QBS tests are now
closed for the matrix above. Assess combined native-AKV coexistence separately. For further Attention
optimization, distinguish quantized Decode, quantized Prefill fallback and
native AKV before selecting an implementation. The rejected grouped-PV
candidate remains disabled: it did not improve complete-call VCS latency.
