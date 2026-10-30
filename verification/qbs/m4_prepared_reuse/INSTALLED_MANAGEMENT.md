# Installed preparation-cache management checks

Run from the verification worktree:

```sh
python3 -m unittest discover -s verification/qbs/m4_prepared_reuse \
  -p test_installed_management.py -v
```

On 2026-10-27 all three tests passed. They do not modify the production
implementation or the pinned inputs of the concurrently running Q/V/K VCS job.

## What is checked

1. All four canonical headers are byte-identical to the installed llama.cpp
   copies: cache, runtime wrapper, graph policy and RVV byte operations.
2. The existing 8064-check cache-management suite compiles against the actual
   canonical `q8_K-prepared-cache.h`, rather than a generated experimental
   header. Only a namespace compatibility shim is supplied. UBSan is enabled.
   This is a host run: the portable byte-operation branch is used. Separate
   RVV functional/CSR tests and the VCS experiment cover vector byte operations.
3. The actual GGML graph/tensor APIs and canonical policy header pass 268
   checks under UBSan. The matrix includes Q2_K/Q3_K/Q4_K/Q5_K/Q6_K weight
   types and 1, 2, 3, 4, 7, 8, 15, 32, 36 and 64 input rows. Q/V/K selection
   and overlapping writes are checked. Independent chains with 0, 1, 126,
   127, 128 and 129 intervening operators check the bounded graph scan.

The format callback in the policy test deliberately admits five types. It
tests the graph-policy behavior after capability admission, not the real
hardware capability query, repacking, arithmetic or performance of each type.
The runtime wrapper separately checks QBS planning and refuses wide-M layouts.
M greater than 32 in this policy test does not mean every group is cached:
the production wrapper admits only the first eight four-row groups.

## Decisions retained

- Keep the feature opt-in while complete projection timing is pending.
- Do not enlarge the hardware activation SRAM or ignore its capacity checks.
- Keep exact owned-input comparison; graph identity alone cannot justify hits.
- Keep non-RNE, nonzero restart, multiple-worker and unsupported-layout paths
  uncached. Single-row tails retain their existing quantization path.
- Bound graph planning to 128 visited nodes. Missing a reuse opportunity
  beyond that limit is allowed; it must not authorize unsafe reuse.
- Keep the 1 MiB software payload limit, eight entries and prefix admission.
  Larger batches and K beyond the admitted limit remain functional through
  the original path, not through unproven cache capacity expansion.

These checks strengthen installation and policy evidence. They do not close
the remaining full-projection performance gate or establish model tokens/s.
