# e32/m4 Full5985 Source Model and Expected-Block Reuse

Status: **SOURCE_MODEL_COMPLETE; COST_HOLD; no compile/reference/DUT admission.**

The one authorized Python source/math construction returned numeric child 0
in 5.880766 seconds, without timeout. It did not invoke a compiler, compiled
Host test, Spike, DUT, or query a running task. No sealed predecessor or RTL
was changed. This is data-model evidence, not compiled-C or architecture PASS.

## Identity and Receipts

- Original archived ELF SHA256: `4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9`.
- Original assembly SHA256: `878be135cd439f7a481312e7afd4b2ce4203806ce5f92c453000918f75c7316b`.
- Original recovered C SHA256: `7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.
- The C has an existing binary-equivalent reconstruction proof; it is not
  claimed to be byte-identical original C or Linux execution.
- Hilbert's static source NO_BLOCKER is bound by
  `../full_e32_m4_static_review01/REVIEW.json`, SHA256
  `2377a847cfa82822816620ba4a1e3e617c0b922b0f4a993274eb8f7b268da17d`.
  That review covers the static plan, not this newly constructed model.
- All 12 inherited source/evidence pins, static PLAN/SOURCE_PINS, review and
  model were checked before and after construction: 16 unchanged input pins.
- `invocation.json`, `child.json`, `stdout.log`, `stderr.log`, `execution.json`
  record the actual single construction. `execution.json` SHA256:
  `5e44dab9f42c0de387b224f2b62041a38a958f5404a29822ed2a118308b1e111`.
- `model.py` SHA256: `920b1110cc5114b8582ca3a42080f0ac41fbf6d78176ecb0f2ab8a7a86d43ae8`.
- `generated01/result.json` SHA256:
  `620787e985a2e829b70dbee457f67bac3d7e14d31afbc0b5bea1b25c53aac4eb`.
- `generated01/reuse.json` SHA256:
  `edccb19594976ca3bb7503eba2990b6b2283f88d459b5cf5e81fa4794425353c`.

Actual command, already completed and **not to be repeated into these outputs**:

```text
python3 -B verification/fpga/current_board_review/arithmetic_restart_original/full_e32_m4_source_model01/construct.py
```

## Original Scope Kept

SEW32, CAP128, LMUL4, VLEN1024, vtype18, four physical registers per group.
Every original call remains in `seed/op/VL-index/mask/start-index` order,
including repeated tuples and VL0 calls: 5985 calls, 35 ops, three seeds,
766080 uint32 results, 11970 uint32 guards, 5985 required returned-vstart
checks and 77805 dynamic original helper instructions. The latter two are
requirements here, not measured CSR/instruction retirements.

`generated01/calls.json` retains all call identities, nine IDs, input/output
hashes and per-call reuse counts. No calls were deduplicated. The original
458 static helper instructions / 1688 bytes remain bound by original ELF/S
pins; this task did not rewrite or port them.

The source-style and separate mathematical implementations compare all
778050 typed result/guard words. Mathematical integer operations use
independent bit arithmetic/restoring division; 931 corner combinations also
agree. RNG remains 64-bit xorshift, with truncation to uint32 only at original
assignments. `seed_inputs.json` retains all 1104 source-order assignments,
including initial writes subsequently overridden by source special cases.
This does not assert that original GCC emitted those assignments in that
source order; future actual sites must be audited separately.

FP values come only from the original 640-entry uint32 table, checked against
ELF offset 0x15b0. The eight original inputs are address-bound at 0x1590;
their byte pattern is not unique in the ELF. No host floating arithmetic is
used. All 1890 FP calls include 256 ordered writes a[0],b[0],...,a[127],b[127]
even when VL0 or all results remain unchanged: 483840 SW obligations. The
source and periodic mathematical write ledgers agree exactly. The diagnostic
period table is not permission to hoist future runtime writes or required
eight immutable input reads out of a call. Each next seed restores full RNG
inputs before its integer history. Original scope has **no fflags oracle**.

All 2205 mask groups retain 128-byte clear followed by original selected-bit
SB order and cumulative byte values. `mask_source_ledger.bin` proves source
clear events 282240 and selected SB 154350, independently reconstructed.
Proposed future clear lowering is 16 exact SD per group, 35280 total; upper
112 mask bytes remain zero, physical backing128B, actual vlm footprint16B.
It is not a replacement of selected SB with a final-mask copy.

Each call's initialized and checked output remains exactly 520B: 128 results
plus two uint32 guards, both 0x0000005b. There are 65 complete scalar words:
first word is front guard + element0; last word is element127 + rear guard.
The original 1026-uint32 backing and original mismatch fallback remain future
port obligations. No actual output access may extend beyond byte519.

## Exact Dictionary and Losslessness

Full uncached gold is 3112200 bytes, kept offline. For output G[c], define
block j as G[c][64*j:64*j+64], padded with zero only for its ROM representation.
Canonical ID equality means equality of **all 64 bytes**, not a hash match.
The ninth block has 8 valid bytes and 56 representation-only zeros. Concatenate
nine dictionary blocks, then take exactly 520B: this equals every original
source/math output, checked for all5985 calls. The padding is never an actual
output read/write or an extra oracle.

| Component | Exact size |
| --- | ---: |
| Unique 64B blocks U | 2252 |
| Dictionary | 144128 B |
| 53865 uint16 IDs | 107730 B |
| Three masks + original FP table/inputs | 2976 B |
| Listed ROM components | 254834 B |
| Plus conservative static memory reserve | 168096 B |
| Total planning envelope | 422930 B |
| Slack below 1MiB | 625646 B |

The reserve includes 64KiB stack, 64KiB text, 12448B original backing,
12288B runtime/HTIF, 8192B other rodata and 4096B alignment. Some rodata is
conservatively counted twice. This is not an actual map/stack measurement.
Full gold, call JSON and diagnostic ledgers are host artifacts, not runtime ROM.

## Same-Call Reuse

Every scheme below reconstructs all520B for each call and retains **389025
actual output LD** obligations. Only immutable expected-ROM loads differ.

| Expected-load scheme | Expected LD | Saved LD |
| --- | ---: | ---: |
| Uncached 65 per call | 389025 | 0 |
| Ideal once per distinct block in each call | 120393 | 268632 |
| Previous-full-block cache | 124041 | 264984 |
| Best single persistent block, selected per call | 123849 | 265176 |

Distinct first-eight-block counts 1..8 have call populations
3063,1389,156,249,522,138,186,282. Every last-block ID differs from every full
block ID in that call; the all-nine populations are consequently shifted by
one. There are 33123 adjacent full-block cache hits, 14757 full-block loads
(5985 compulsory first blocks +8772 later misses), and 5985 uncached final
word loads. Ideal full-block reuse hits are33579.

### Narrow Source Candidate

The sensible source candidate is one previous-block cache, reset on each
call. Keep eight local uint64 expected values and the previous canonical ID.
For each of the eight full blocks, load the current ID; refresh those eight
expected values only if the ID differs. Regardless of a hit, perform eight
distinct actual output reads at that block's offsets and compare all eight
words. Read and compare the last actual/expected word separately. All output
and ROM accesses should use exact-size memcpy idioms, not type-punned uint64
pointers into uint32 objects. No compare may short-circuit the remaining
actual reads. Accumulate mismatch, then use the unchanged original typed
failure fallback with original error counting and tuple fields.

Correctness invariant: before each comparison, cached expected[k] equals
dictionary[current_ID][8*k:8*k+8]. On a miss this follows from the eight
loads; on a hit it follows from exact canonical ID equality. Actual output
data never enters the cache. Thus every original result and guard bit is
compared at its original location, including signed zero and NaN bit patterns.
There is no aliasing or overflow dependency: uint64 comparison is bitwise,
all full-block accesses lie in bytes0..511 and the final load is512..519.

Eight cache values plus one actual temporary, ID, bases and accumulator may
fit integer registers, particularly after the FP setup function returns, but
GCC register allocation is unmeasured. A stack-spilled cache can replace ROM
LD with stack LD and erase the benefit. Caching all unique blocks needs up
to64 expected-value registers and is only a benefit bound, not a feasible
register plan. The selected-single-block alternative saves only192 further
LD over the adjacent scheme but adds11970B ID metadata and normally5985 ID
loads, so it is not justified here.

### Cost Gate Remains HOLD

The earlier 3384640 illustrative firmware anchor and 3699825 illustrative
static allowance are analogies, not actual e32/m4 CFG or measured retirement.
Removing even the ideal268632 expected LD alone gives3116008 /3431193,
still above3M. The adjacent candidate gives3119656 against the lower anchor,
before new cache-control costs. There are41895 later full-block ID decisions;
comparisons/branches, cache updates and possible spills must be charged.
Avoided dictionary address calculations can offset some of that overhead,
but cannot be treated as known GCC instructions or a proved3M budget.

Therefore exact repeated gold makes a small immutable cache mathematically
valid and materially useful, but **does not establish that this single change
passes the3M gate**. No compile or reference is proposed as a blind cost probe.
The next decision requires a reviewed source-level cost argument that closes
the remaining gap; current complete scope, bounds and HOLD are unchanged.
No caching rule or expected-LD contract of sealed e64/m4 or e32/m2 was changed.
