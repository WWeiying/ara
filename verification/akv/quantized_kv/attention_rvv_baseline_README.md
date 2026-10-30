# Attention With An Equally Optimized RVV Baseline

## Why This Additional Comparison Exists

The original production decoder happens to compile as scalar code with the
recorded GNU flags. Replacing it is a software improvement, not a new hardware
mechanism. The candidate-only decoder experiment measures the combination of
that improvement, QBS QK and cross-head V sharing. It must not attribute the
whole speedup to QBS or compare that speedup with an already vectorized baseline.

This successor gives **both** schedules the same independently accepted RVV
Q8_0 decoder. It retains the production RVV Q4_0/Q8_0 dot products in the
ordinary schedule and QBS DIRECT in the shared schedule. Query quantization,
online Softmax, F32 PV, normalization and output checks are unchanged.

| Experiment | Ordinary V decode | Shared V decode | Measured distinction |
| --- | --- | --- | --- |
| Original public entry | Original scalar | Original scalar | QBS/shared schedule including admission |
| Candidate-only RVV decoder | Original scalar | RVV | Combined decoding and QBS/shared improvement |
| This successor | RVV | Same RVV | QBS/shared improvement after equal V vectorization |

This last comparison still combines QBS QK and cross-head sharing; it is not
an isolated QBS-only or sharing-only ablation. Mapping and admission are timed
in the shared path. Each run remains a real captured six-head group, not a
whole model or an unchanged whole GGML operator.

Compare paired cycles within this ELF. Compared with the candidate-only
successor, it also removes the local bindings-copy wrapper; a difference between
the candidate cycles of those two ELFs is not a decoder-only measurement.

## Implementation And Fairness Checks

`attention_rvv_baseline_main.c` supplies one finite decoder and renames only
the decoder symbol while including the unchanged common benchmark. Therefore
the ordinary `value` callback and the shared runtime's binding select exactly
the same function. The public runtime, admission and error handling are not
intercepted. Captured inputs have already passed the decoder's finite/block
preconditions; production selection must continue enforcing them.

The builder reuses all original primitive/runtime/data objects and replaces
only the main object in a fresh output directory. It checks that the old scalar
decoder and host reference executor are absent from the final ELF, both original
RVV dot products and the QBS executor remain, and the selected decoder contains
the expected RVV operations. Compilation uses the inherited flags, including
the unchanged floating-point contraction policy. All dependencies, parent
artifacts and executable identities remain pinned.

Two builds and result directories use the prefixes:

- `verification/out/akv-quantkv-rvv-baseline-attention-q4-build-20261024-01`
- `verification/out/akv-quantkv-rvv-baseline-attention-q8-build-20261024-01`
- `verification/out/akv-quantkv-rvv-baseline-attention-q4-20261024-01`
- `verification/out/akv-quantkv-rvv-baseline-attention-q8-20261024-01`

The labels refer to K encoding; V is Q8_0 in both. Each retains D128, all six
Query heads of KV head0, visible KV128 and capacity256. The unchanged worker
checks ABBA results, 768 output words per trial, guards, FCSR/VCSR, actual QBS
work, source/image identity, independent backend/CVXIF/AXI evidence and exit.

No accepted timing is recorded here before terminal independently checked
results exist. Earlier production-baseline results remain valid under their
original scope and are not overwritten or silently relabeled.
