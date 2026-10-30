# Hint-first integration review

Reviewed against the installed runtime on 2026-10-29. This is an integration
decision record, not evidence of completed production integration or speedup.

## Correct insertion point

The caller is `ggml/src/ggml-cpu/repack.cpp`, not the architecture-specific
`arch/riscv/repack.cpp`. Its ordinary four-row preparation loop calls
`ggml_riscv_q8_K_prepared::state::prepare`. The state implementation resides in
`arch/riscv/q8_K-prepared-reuse.h` and owns the exact-byte cache.

If the cycle experiment justifies promotion, store eight preferred-slot hints
in that worker-local state. Pass the group-specific hint to `bytes.get` and
`bytes.put`. Do not change the identity key, rewrite graph scheduling, or move
this optimization into the hardware descriptor. On a 64-bit target eight
`size_t` hints occupy 64 bytes per worker, excluding structure padding. This is
software state, not additional synthesized storage.

## Existing eligibility must remain unchanged

| Layer | Current gate | Required behavior after integration |
|---|---|---|
| Build/runtime | QBS support, M4 preparation and prepared-cache opt-in | Preserve all switches and original fallback |
| Graph policy | Single worker, valid graph and nonzero epoch | No multiworker sharing or graph-lifetime claim |
| Operator | Supported Q2_K/Q3_K/Q4_K/Q5_K/Q6_K MUL_MAT, Q8_K preparation, not wide-M | Do not route Q8_0 or wide-M through this cache |
| Input | F32, contiguous, at least four rows, ne2=ne3=1 | Strided and multidimensional inputs keep existing paths |
| Group | Group indices 0 through 7 | Later full groups and residual rows stay uncached |
| K | Positive, divisible by 256, at most 6144 | Preserve the entry-size bound |
| Controls | RNE and vstart=0 | Preserve numerical fallback and sticky FFLAGS |
| Lifetime | Compatible graph, epoch, source and lookup policy | Preserve begin/finish clearing rules |
| Cache hit | Same numerical/layout key, sizes and exact input bytes | A hint alone can never authorize reuse |

For K=6144 the saved input is 98,304 bytes and packed output is 28,032 bytes,
or 126,336 bytes per entry. The next K quantum, 6400, needs 131,600 bytes,
exceeding the 128-KiB maximum. Do not remove the software K cap merely because
the underlying QBS arithmetic supports larger matrices.

## Lifecycle and failure behavior

- `begin` clears entries when graph, epoch or source changes, or lookup is
  disabled. `finish` clears them when no later consumer justifies retention.
- Hints may be invalidated during those existing clears for clarity. Correctness
  cannot depend on invalidation: replacement and duplicate-conflict removal can
  independently leave stale hints, which must still pass full validation.
- A miss computes exactly once. Allocation failure must not trigger a second
  quantization, alter the produced output, or destroy unrelated valid entries.
- Only vector-produced results are stored by the existing wrapper. The generic
  producer remains a valid output-producing fallback, without adding entries.
- Cached FFLAGS are ORed into the incoming sticky flags; rounding mode remains
  part of eligibility. Searching and copying use nonsaturating byte operations.
- Entries contain owned snapshots. Pointer identity, graph identity and group
  identity are not substitutes for input-content equality.

## Evidence and remaining gates

The host differential tests cover stale hints and payload conflicts. The real
activation-key replay covers several input groups, but uses opaque payloads and
does not simulate graph lifetime. The running VCS benchmark uses the real
quantizer and checks all returned bytes, flags and protocol events. It measures
three groups reused by three consumers, not the graph-policy scan itself.

Before changing the installed runtime:

1. Accept the actual VCS result and evaluate both ABBA pairs, not just their mean.
2. Measure single-group reuse and no-reuse controls. Extra hint handling can
   outweigh savings when an ordinary first-slot search already succeeds.
3. Only if useful, derive an isolated runtime variant with worker-local hints.
   Reuse the existing paired model tests to compare logits, token choices,
   FCSR/VCSR, graph schedule, native command sequence and cache hit/miss totals.
4. Keep exact-byte verification even if it limits the achievable speedup. A
   pointer-only shortcut would be a different, less robust mechanism.

Do not aggregate this experiment's preparation-only ratio with the existing
QBS-vs-RVV matrix speedup or claim the same ratio for model execution.
