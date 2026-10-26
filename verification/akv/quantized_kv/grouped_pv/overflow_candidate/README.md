# Isolated stride-check candidate

This directory does not modify the production grouped-PV implementation.
The measured grouped-PV path contains a per-token `divu` for
`stride > (SIZE_MAX / sizeof(float) - dim) / (heads - 1)`.

Let `factor = heads - 1` and `limit = SIZE_MAX / sizeof(float) - dim`.
For nonzero factor, the original predicate is equivalent to the mathematical
product `stride * factor > limit`. If size_t multiplication overflows, the
mathematical product necessarily exceeds limit. Otherwise compare the exact
product to limit. For factor zero, both predicates are false. The candidate
uses the compiler's defined unsigned multiplication-overflow builtin and
retains the original division predicate for unsupported compilers.

The surrounding guards must remain unchanged: valid head count, dimension,
stride, mask, pointers, alignment, aliasing and output range. This is not
permission to remove the public leaf validation or to hoist checks across
callbacks that can modify inputs.

Validation:

```sh
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/grouped_pv/overflow_candidate \
  -p test_stride_check.py
```

GCC and Clang each check 1,010,575 cases, including every supported dimension
and head count at the quotient boundary, SIZE_MAX, zero, and deterministic
random full-width values. Undefined-behavior instrumentation uses trap mode;
the host shared UBSan runtime is unavailable. RISC-V GNU compilation checks
that the candidate contains `mulhu` and no divide/remainder instruction.

These checks passed on 2026-10-26. They are arithmetic and code-generation
evidence, not a new complete-call performance result. Integration and a fresh
paired measurement remain outstanding. Keep grouped-PV default OFF.
