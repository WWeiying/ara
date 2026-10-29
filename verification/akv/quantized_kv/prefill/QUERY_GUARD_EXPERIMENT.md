# Remaining Prefill Query-domain branch experiment

## Source finding

The current `software/akv/experimental/quantized_kv/selection_strided.h`
already reduces each Query block to its largest absolute integer bit pattern
before checking nonfinite/range conditions. The extra Query rows checked by
`prefill/admission.h` still test nonfinite values inside the 32-element loop.
These are two distinct scans: one Decode-style selector checks the maximum
visible-prefix row and the KV union, then Prefill checks the remaining rows.

`query_guard_experiment.py` derives a renamed isolated candidate from the exact
current Prefill header. It removes only the per-element nonfinite branch and
checks `amax >= 0x7f800000` after the block. Bounds, block order, return reasons,
range limits, masks, KV validation and fallback policy are unchanged. It does
not introduce vector instructions or change quantization.

With the sign bit removed, every infinity/NaN bit pattern is at least
`0x7f800000`, and every finite bit pattern is smaller. Therefore the maximum
has this property exactly when at least one element does. No floating-point
comparison is needed, including for signaling NaNs. Input extent and normal
memory contracts must still hold because the candidate can finish reading a
block after encountering an invalid element, whereas the original returns
immediately.

## Host evidence

Accepted run: `verification/out/prefill-query-guard-20261029-02`.

- Clang AddressSanitizer and UndefinedBehaviorSanitizer enabled.
- Original 20-case admission suite passes as a prerequisite.
- 1664 directed paired comparisons: four query rows, all 32 element positions,
  13 special/boundary bit patterns in the final block of the final head.
- 2000 deterministic randomized block comparisons.
- Same reason codes, successful output plans, unchanged rejected plans,
  untouched output storage and unchanged sticky floating-point exceptions.
- Dependency hashes captured before compilation and rechecked after execution.

The original 20 cases exercise the original implementation; candidate-specific
evidence is the 3664 paired comparisons. This is host semantic evidence, not
new RTL coverage or measured speedup. The earlier host run used the same test
logic but lacked full dependency pinning; use the second run for this milestone.

## Next gate

Inspect the generated GNU RISC-V code to establish whether the compiler already
removes the branch. If the code differs use a paired, bounded real-input VCS
experiment including complete admission and execution. Do not promote based
only on reduced C-level condition count. Preserve ordinary fallback and both
Q4_0/Q8_0 K-cache configurations. Production code is unchanged.

The cache-hint experiment was rejected after a measured regression. This
candidate must pass the same actual-cycle criterion; host equivalence alone
does not justify enabling it.
