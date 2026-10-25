# Untimed Verification Successor

Preparation only. No native build, simulation, timing claim, checker change or
timeout increase. The uninterrupted six-call H/S/B/B/S/H scope remains intact:
six heads, D128, visible KV128, actual strided captured inputs, full original
golden/tolerance, repeats, guards, CSR snapshots and all 36864 output hex chars.
Completion within three hours is **not promised**.

## Transform API

`render.py` exposes `render(original: bytes) -> bytes`, `inverse(generated)` and
`provenance(original, generated) -> dict`. The frozen Q4 and Q8 fasthex mains
have the same required SHA256:

`8e5d8edf7aa79ae615a9eb2f6b9cecc8f27e1fc93e827f88ca4203788c34324a`

`ORIGINAL` points to the retained Q4 fasthex build source. Callers may read the
identical Q8 source instead; every input byte is still hash-locked. There is no
builder, runner, private import override or automatic image acceptance here.

Five exact substitutions are confined to the block starting at `float max_abs`
and ending at `if (errors) return 1`. Everything before that block is identical,
including both rdcycle sites, final drain, FCSR/VCSR capture, baseline FCSR,
status/map/selection/count checks, all timed code, declarations and includes.
Everything after the block, including final suite PASS, is identical too.
Inverse transformation must recover the full original hash, rejecting edits
inside or outside the allowed region.

Within that region, explicit `__builtin_memcpy` copies four bytes to stack-local
uint32 words. A single `y_word`/`baseline_word` pair serves the existing bit
difference count and H/S equality check; a previous-mode word is read only when
`seen[mode]` was already true. Baseline initialization still precedes extraction.
Padding, maximum-error print arguments and output emission use the same explicit
bit-copy. No float conversion, aliasing cast, global array, tolerance change or
new FP operation is introduced. Original floating-point predicates, assignments,
error additions, guard loops, printf format strings and fasthex emitter remain.
Do not globally change `bits`, `memcpy`, compiler optimization or FP flags.

## Host Tests

From the signoff root:

```sh
python3 -B -m unittest discover -s verification/akv/quantized_kv/untimed_verify -p 'test_untimed_verify.py' -v
```

Tests compile two host fixtures using the actual extracted original/generated
verification-and-printing blocks, not separately handwritten implementations.
GNU host GCC uses `-O3 -std=c11 -Wall -Wextra -Werror -fno-builtin
-fno-tree-vectorize -fno-fast-math -ffp-contract=fast -frounding-math
-fsignaling-nans`, links `-lm`, with 60-second compile/run bounds.

The 576 cases cover signed zeros, minimum/maximum subnormals, normal boundaries,
infinities, signed quiet/signaling NaNs with payloads, random words, three modes,
first/repeat state, trial-zero baseline initialization, initial error counts,
golden/tolerance failure, exact-bit differences, padding and both guard sides.
They compare full stdout byte-for-byte, every expected error count, all raw
baseline/previous/seen state bytes, captured host FP exception flags and sticky
divide-by-zero preservation. Special output payloads are independently checked.
Mutation tests reject input, timing, CSR, tolerance, output and inverse drift.
Host fenv agreement is not native FCSR/VCSR or runtime performance acceptance.

Prepared host result: **7 tests PASS**, including 576 actual-block cases and
442368 output words per implementation; no cross compilation or EDA performed.

## Parent Build / Review Requirements

1. Reuse the pinned production primitive/runtime/data objects and accepted FP
   flags. Generated source provenance must prove the exact unchanged prefix,
   suffix and timed-source SHA256; no timing-source or input substitutions.
2. Inspect linked assembly: the seven fixed-size builtin-copy sites should
   become raw loads/moves, with **no out-of-line memcpy calls attributable to
   these post-window copies**. Cached y/baseline words should be reused; the
   original tolerance arithmetic must remain. Remaining timed/library memcpy
   calls are legal and must not be globally removed. UART still emits eight
   lowercase characters per word through the unchanged emitter.
3. Compare link maps: unchanged Query/K/V/golden/scale, output, workspace,
   context, baseline and previous-result addresses/alignment/sizes; no added
   global buffers. Preserve linked primitive object identities. Recompiling main
   may change stack use, instruction placement or register allocation even with
   identical timed source. Audit the timed instructions/relocations separately;
   this transform does not assert machine-code or cycle identity.
4. The old TIMEOUT and old image are immutable history. Canonical promotion
   means its old source-manifest validator cannot simply be reused. Eventual
   execution must use the reviewed **new canonical image and new image receipt
   consumer**, with actual source/image checks, not a hash waiver. Label it a
   successor image/run; do not attribute any difference solely to this transform
   or turn the old Q4 TIMEOUT into PASS.
5. Retain the exact six-call stdout/raw numerical contract, independent UVM/AXI
   checks, all work counts and 10800-second bound. This directory changes none
   of those consumers. Build/run adapters remain parent-owned future work.

Freeze these source files after host review; later changes require a successor.
