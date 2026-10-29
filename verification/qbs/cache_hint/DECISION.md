# Decision: do not promote hint-first cache lookup

The completed VCS experiment passed functional and protocol acceptance but did
not show a performance benefit. Preserve the existing production cache.

## Measured result

Run: `verification/out/cache-hint-vcs-20261029-02`.
ELF: `verification/out/cache-hint-build-20261029-03/cache_hint.elf`.
The same ELF contains both implementations; source/image pins matched before
and after execution. An independent replay of the result parser, protocol
receipt and all 963 recorded input pins also passed.

| ABBA position | Implementation | Preparation cycles |
|---|---|---:|
| A1 | Original | 203325 |
| B1 | Hint-first | 205987 |
| B2 | Hint-first | 205381 |
| A2 | Original | 202364 |
| Mean A | Original | 202844.5 |
| Mean B | Hint-first | 205684.0 |

The candidate takes 1.39984% more cycles on average. The adjacent pairs are
1.30923% and 1.49088% slower. Both versions have three producer executions,
six hits, three misses, three stores, 136800 copied payload bytes, FCSR=17,
VCSR=5 and zero data/canary errors. Requested comparison lengths fall from
442368 to 294912 bytes, but this is not a traffic or elapsed-time measurement.

VCS reported 3837.950 CPU seconds. The first run remains a separate timeout,
not a partial PASS. Its partial slightly favorable result must not be mixed
with this run: checking code and executable layout changed between builds.

## Interpretation

The hypothesis was that eliminating earlier mismatching slot comparisons would
reduce preparation cost. The candidate does eliminate those comparisons, but
does not improve this measured workload. Failed RVV byte comparisons can stop
at the first chunk, while matching entries still require the full comparison
and output copy. The candidate also adds hint handling and changes generated
control flow. These are plausible explanations, not a proven cycle-level
allocation of the 2839.5-cycle difference. Instruction-layout/cache effects
have not been isolated. Do not claim that every possible hint implementation
or every input shape must be slower.

The current evidence does not justify additional runtime state, switches,
integration and model regression for this candidate. Single-group and miss-only
promotion gates are therefore not pursued now; they were required only if this
candidate first showed reproducible benefit. Nothing is enabled by default or
installed into the production backend. No RTL changes were made.

## Evidence identities

| Artifact | SHA-256 |
|---|---|
| Result | `8804adc3466cd9296fc46f3a9ab24c54bf1c2bc77e02d3fd7f99ade55c0c3e27` |
| Raw VCS log | `3cb793d617b25a26fb29058bcaf66b90cfdf8fda495d28779d6ee49e226327e6` |
| Protocol result | `6e7881f0224f67a6deccc901b5ccf79e9467f64e578c6d6dd2e6c9d4c95da742` |
| Source-pin inventory | `bce58436018b8c84c61191f0f8b49f43a89d38958e6dd9c0a0041f07ed8554e7` |

## Next priority

Keep the accepted parallel activation sums, prepared-input reuse, register-PV,
grouped Prefill and hardware retirement improvements unchanged. Shift effort
back to measured preparation/execution/copy costs in real runtime paths rather
than reducing a proxy counter. In particular, broader model attribution remains
unfinished: QEMU graph/schedule equivalence proves functionality, not RTL model
speedup. Use representative RTL slices to qualify any next candidate before
production integration, and do not multiply this preparation-only experiment
into matrix or whole-model acceleration claims.
