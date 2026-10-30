# V reuse: numerical domain and copy cost

## Numerical prerequisite

`test_q8_value_domain.c` checks all 63,488 finite binary16 bit patterns against
all 256 signed-byte values, under four host rounding modes. It constructs the
binary16 value from an integer significand and a power of two and compares the
F32 product with an independent long-double integer-product construction. It
checks signed zeros and verifies that the initially set division-by-zero flag
remains the only exception flag after every complete rounding-mode sweep.

Result: **65,011,712 products PASS**. Command:

```sh
/usr/bin/clang -std=c11 -O2 -Wall -Wextra -Werror -frounding-math \
  -ffp-contract=off verification/akv/quantized_kv/prefill/test_q8_value_domain.c \
  -lm -o /tmp/q8-value-domain
/tmp/q8-value-domain
```

The test establishes the arithmetic-domain premise used by the finite-Q8_0
cache proposal. It does not validate RVV instruction execution, VCSR, memory
access bounds, the compiler's RISC-V sequence, or arbitrary decode callbacks.
Native paired VCS runs separately check the actual RVV decoder and outputs.

## Native copy path

The Q4 candidate ELF in `verification/out/value-cache-q4-build-20261029-02`
contains calls from `vcache_value` to `memcpy`. The linked implementation has
an aligned eight-byte scalar load/store loop and an unaligned byte loop. It
is not an RVV copy. This is a code-generation fact, not a measured stall
breakdown or proof of the candidate's final speed.

For the two-group D=128 example, the cache fills eight rows and hits four rows.
Each row contains 512 decoded bytes. The current copy-based candidate adds
eight cache-store copies and four hit copies, totaling 6,144 copied bytes.
Those copies each read and write data; they are not 6,144 bytes of measured
external memory traffic. It eliminates only four 136-byte compressed-row
decodes. The computational saving may outweigh these costs or may not; use
the complete-call VCS result to decide, not decode counts alone.

The first copy-based experiment is deliberately retained as a complete
measured candidate, with original and candidate in the same ELF. Its files
and inputs are sealed while workers run. Do not rewrite it to implement a
different cache and then compare mismatched evidence.

## Better transport if copying dominates

A successor design can return a read-only value-row pointer to the scheduler:

1. On a first visit to a cacheable token, decode directly into its cache row.
2. On a hit, return that row without copying it to the online scratch buffer.
3. For tokens outside the bounded cache, decode into existing scratch and
   return scratch instead.
4. Consume the returned pointer for every participating row before the next
   token callback; do not retain scratch pointers past that interval.

This does not change the QK or online Softmax/PV arithmetic order. The current
callback ABI writes into caller-provided scratch, however, so pointer-return
transport requires a distinct internal scheduler entry or a reviewed optional
callback. The generic API must retain its existing semantics. A specialized
cache entry still requires a known pure decoder, per-head/per-call reset,
immutable inputs, and bounded disjoint storage.

Do not implement a global cache, persist input pointers across model calls,
or substitute a larger unbounded cache. Before promoting pointer transport,
compare all outputs and flags, validate noncached-token lifetimes and failure
behavior, then measure against the original production entry, not merely
against the potentially slower copy-based candidate.
