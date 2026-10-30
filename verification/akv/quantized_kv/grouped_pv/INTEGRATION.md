# Grouped PV: integration gates

This is a candidate optimization, not an enabled production path. The leaf and
host tests are developed outside the current model worker's sealed SDK inputs.
Do not edit production headers, runtime objects or GGML while that worker runs.

## Hypothesis

The current shared schedule decodes V once per token, but each head's MAD helper
loads V again. A maximum update also calls scale before MAD, loading/storing Y
twice. A grouped leaf can retain V across heads and perform separate multiply
then fused multiply-add on the same loaded Y. It must not overwrite V with a
destructive multiply-add instruction. Ordinary RVV resources implement the leaf;
this hypothesis needs no new ISA or additional hardware compute array.

For H6/D128/T128, the source-level V operands of MAD total 384 KiB. Loading one
shared V row per token would total 64 KiB. This is not a claim about cache misses,
AXI traffic or latency. Each actual maximum update can additionally avoid one
512-byte Y load and one 512-byte Y store. The update count must be measured.

Earlier pre-field-copy diagnostic PC intervals motivate investigating PV, but
are not the current phase percentages. The candidate must be measured against
the current field-copy implementation on both arms.

## Contract

Preserve per-head token order, score multiplication, addition of zero mask,
maximum comparison, expf, sum recurrence and final normalization. Compute
scalar coefficients before entering the RVV leaf. Preserve a separate rescale
predicate: multiplying by one is not a substitute for the branch, and a zero
coefficient is not permission to skip an original FMA.

The leaf performs `round32(Y * ms)` only on the original rescale branch, then
`fma(V, vs, Y)`. It preserves sticky floating-point flags and VCSR. Current
production admission continues requiring RNE and its guarded input domain.
All values stay within validated output/V extents, including odd head counts,
strided output padding and vector-length tails.

Arbitrary existing scale/mad callbacks may have observable side effects. Do
not silently replace them. Add an explicit grouped-update opt-in with a new
entry point or an optional separate parameter, keeping the old C ABI and its
callback schedule intact. Only the production arithmetic bindings qualify.

## Promotion sequence

1. Compare independent scalar reference with leaf results/flags/guards in host
   tests; inspect actual GNU RVV code. Host tests do not prove RVV execution.
2. Run the leaf on a RISC-V reference target with the real capture and boundary
   cases. Compare actual bits and FCSR/VCSR, not only final generated text.
3. After existing consumers finish, integrate the explicit opt-in into shared
   online scheduling/runtime and the real GGML adapter. Preserve fallback before
   admission and error handling after execution begins. Keep QK, V-decode,
   quantization, gather and command counts unchanged.
4. Measure a fresh paired complete Attention workload on VCS, with current
   field-copy present on both arms. Check original gold, mirrored repetitions,
   CSR, guards and protocols; report spills and any lost performance.
5. Retain in the real backend only after useful whole-call benefit and numerical
   validation. Do not substitute a leaf-only benchmark for integration evidence.

The primary QBS/AKV goal also requires checking projection and F16 Attention
paths. This candidate is one work item, not a redefinition of that whole goal.
