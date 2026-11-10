# Experimental M4 Retained-Maxima Preflight

API: `qbs_experimental_m4_preflight::quantize(const float *, void *, int64_t)`
in `m4_preflight.h`. Its boolean matches the accepted producer: true means
vector production, false means generic production; both produce complete output.
The caller supplies four contiguous F32 rows, K divisible by 256, aligned and
disjoint output, enabled RVV state and zero vstart, as for the original helper.
There is no runtime selection, device probing, cache ownership or allocation here.

The dependency is the **accepted llama** commit
`da56aa750559c180d631b466de983ff2bb5d54d9`, specifically
`ggml/src/ggml-cpu/arch/riscv/q8_K-m4-packed.h` and its dependencies. Include the
frozen `ggml/include`, `ggml/src`, `ggml/src/ggml-cpu`, and its `arch/riscv`
directories. Do not substitute the older SDK packed header without parallel sums.
The new helper calls the accepted `encode`, `sums<true>` and `store` operations.
No existing SDK or llama source is changed by this experiment.

For K<=6144, integer-only full-input validation retains 384 bytes at most of
signed maxima. Strictly greater per-lane updates plus minimum original index
preserve the first global tie. All-zero blocks select positive zero. No output
or FP arithmetic occurs before the entire input passes validation. Domain,
rounding, span, zero-K and larger-K rejection delegate to the original optimized
`quantize<true>`, including its original generic fallback. The encoder, scale
divisions, byte layout and integer sums remain unchanged. Invalid pointers,
overlap and non-block-multiple K are not newly admitted.

Producer identity 4 is reserved for a future experimental selector; accepted
parallel M4 remains tag 3. This file does not alter cache keys or worker policy.
Any future adapter must preserve existing feature switches, single-worker
reuse admission, exact-byte validity, flags replay and invalidation. It must not
let a baseline cache fill hide candidate execution in a comparison.

Correctness harness: `verification/performance/next_mechanism/stage4/m4_preflight/`.
It freezes source archives into fresh `stage4_m4_preflight_*` outputs, links the
actual frozen generic fallback, and compares against packed `quantize<true>`.
The fallback symbol is mechanically namespaced only in its test object so the
harness can check untouched output/flags at fallback entry before delegating.
No benchmark-only numerical implementation substitutes for the shared helper.
Spike evidence is instruction-level correctness, not RTL, graph cycles or a
performance/retention/deployment claim. The helper remains experimental.
