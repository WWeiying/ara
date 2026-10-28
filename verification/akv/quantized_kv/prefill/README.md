# Quantized Prefill Prefix Scheduler Prototype

This directory contains an internal schedule experiment, not an installed
GGML backend or a new RTL mechanism. Existing production sources remain
unchanged while their model acceptance is running.

Rows represent query-token/head pairs for the **same KV head**. Each row has
its own positive visible prefix. The schedule groups adjacent rows with equal
tile extents into 4/2/1 QK callbacks. It never requests a masked score. V is
decoded once per token across the group, and each row retains the original
token-order online maximum, exponential, sum and FMA operations.

For an admitted group, V callbacks decrease from the sum of row prefixes to
their maximum. This is a callback-work reduction, not measured cycle savings.
QK work remains exactly the sum of row prefixes. The prototype reuses the
existing eight-row score workspace and does not allocate a full score matrix.

## Host Tests

From the repository root:

```sh
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -fno-fast-math \
  -ffp-contract=fast -frounding-math -I. \
  verification/akv/quantized_kv/prefill/test_prefix.c -lm -o /tmp/prefix-test
/tmp/prefix-test
```

Clang with `-fsanitize=undefined -fno-sanitize-recover=undefined` also passes.
Both were executed on 2026-10-28 UTC and reported:

```text
PREFIX_HOST_PASS cases=960 bitexact=1 flags=1 masked_qk=0 oracle=1 failure_paths=1
```

The matrix covers 1..8 rows, D=32/64/96/128/256, token limits
1/31/32/33/63/64/65/128, and equal, varying and reverse-varying prefixes.
Checks include bitwise equality with the original head-major implementation,
an independent double-precision softmax oracle, FENV equality, output padding,
exact score/value work, invalid-prefix no-write/no-callback behavior, and
terminal QK/value callback failures.

These are synthetic host tests with deterministic callbacks. They do not
validate QBS descriptors, actual quantization, captured model data, RISC-V
floating-point state, or performance. The caller must establish disjoint
buffers, valid pointer extents, stable metadata and callback ownership before
entering this internal kernel. Zero-visible-row masks remain unsupported.

## Next Gate

Add a bounded adapter for real captured query rows and KV tensors, including
per-row causal masks and up-front admission of the complete output operation.
Compare against the original GGML/row-wise path before connecting native QBS.
Then measure one representative complete call on VCS, including preparation,
K gathering, value decode and output storage. Keep this prototype outside
production until those gates demonstrate correctness and useful benefit.
