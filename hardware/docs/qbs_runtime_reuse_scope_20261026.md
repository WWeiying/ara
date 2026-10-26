# llama.cpp projection reuse: current scope and next decision

## What already exists

This audit reads the current private llama.cpp backend; it does not change
runtime dispatch or RTL. Do not describe existing cross-operation reuse as a
new optimization.

`ggml/src/ggml-cpu/arch/riscv/qbs.cpp` implements:

- `qbs_cross_op_context_enabled`: hardware activation context and cross-op
  reuse default ON; emulation is excluded.
- `context_identity_for_node`: only F32 activation, one row, Q8_K activation
  profile, supported weight/shape and a context-eligible production plan.
- `same_cross_op_identity`: graph epoch, source tensor, source data,
  activation profile, row count and K must all agree.
- `next_context_consumer_matches`: intervening possible writes are barriers;
  expert matrix operations and incompatible matrix consumers stop reuse.
- `ggml_riscv_qbs_prepare_activation_context`: only worker zero with exactly
  one worker. Reuse returns true only after a resident context has been
  established. The last consumer releases the context.

`ggml/src/ggml-cpu/repack.cpp` calls this before quantization and skips the
actual quantization loop when reuse is admitted. Thus this is already a
software-plus-hardware lifetime optimization, not merely a memory traffic
counter.

## Two costs that must not be conflated

| Operation | Current owner | What reuse avoids |
| --- | --- | --- |
| F32 to Q8_K preparation | CPU/RVV quantizer, GGML workspace | Repeated scale, rounding, bsums and stores |
| Q8_K context residency | QBS context and SDK command policy | Repeated activation reads by hardware commands |

Current cross-op reuse requires both conditions. A software cache of prepared
bytes could in principle avoid the first cost even when the second is
ineligible. That cache is **not implemented by this audit** and its benefit
has not been measured.

For the reference 4672-byte context, a row contains 292 bytes per 256-element
Q8_K block. K=1536 therefore needs 1752 bytes for M1 but 7008 for M4. K=8960
needs 10220 bytes even for M1. Capacity is only one eligibility condition;
split-K, layout, gather and command restrictions must also be checked with
the actual planner. These byte calculations are not measurements of resident
RTL state or proof that a given live graph reused anything.

## Model-test scope

The ongoing combined-Zvfh Q8_K preparation model test explicitly disables
cross-op context to isolate the preparation change. It retains per-operation
context and compares identical OFF/ON workloads. It therefore cannot establish
the best default Decode performance or the incremental benefit of cross-op
reuse. Neither can QEMU execution time establish RTL speedup.

Before promoting a faster preparation path, check its coexistence with the
default cross-op policy, including calls which correctly skip preparation.
Use separate child processes for cached environment switches. Preserve
single-row, multi-row and fallback coverage rather than checking only M4.

## Next optimization gate

1. Complete the current same-ELF VCS preparation/projection measurement.
2. Accept the actual model OFF/ON numerical and native-command audit.
3. Check default cross-op ON coexistence in a separate bounded graph/model
   test before changing production selection.
4. For further reuse work, first collect actual graph source identities,
   quantization counts and rejection reasons. Compare whole-call RTL cycles,
   not only logical byte savings or projection invocation counts.

A software prepared-activation cache is justified only if the trace identifies
repeated expensive preparation that current residency cannot reuse. It must
own its storage: GGML's shared workspace can be overwritten by intervening
operators. A safe key also needs layout, shape/strides, quantizer semantics and
source lifetime; a matching pointer alone is insufficient. In-place updates,
graph epochs, cancellation, worker concurrency and quantization side effects
must have explicit handling. Do not relax the existing mutation barriers to
gain apparent hits.

If the unserved consumer is only an FFN down projection with a different input,
there is no repeated-input reuse opportunity just because K is large. Likewise,
existing successful M1 reuse is not evidence for M4 reuse. This distinction
prevents adding cache state and copy overhead without a demonstrated target.
