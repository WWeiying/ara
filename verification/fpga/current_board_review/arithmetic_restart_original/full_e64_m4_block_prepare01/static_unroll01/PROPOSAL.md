# Fixed eight-block comparator expansion: static only, still HOLD

This is the sole proposed source change. No header, candidate ELF, original
source, or sealed artifact is changed. No compiler, reference, or DUT is run.
It follows the current actual CFG, not a measured new compiler result.

## Falsifiable hypothesis

Replacing the eight-iteration comparator loop by eight constant-block
expansions can remove its loop control and expose one reusable dictionary
base and one reusable row-ID base. Keep the ninth block at two words only.
Keep the same 66 volatile actual LDs, 66 volatile expected LDs, and an
OR-of-XOR accumulator with no early return, even for wrong data. Do not
replace it by a checksum, branch-on-first-mismatch, or cached result.

The intended source shape is:

```c
const uint16_t *ids = e64m4_block_ids[ordinal];
uint64_t different = 0;
/* EACH expands the existing eight COMPARE statements with constant offsets. */
EACH(0); EACH(1); EACH(2); EACH(3);
EACH(4); EACH(5); EACH(6); EACH(7);
/* Actual offsets 512 and 520; dictionary offsets 0 and 8 only. */
TAIL_TWO(ids[8]);
return different != 0;
```

Each `EACH(k)` would have its own scoped pointer to
`e64m4_dictionary[ids[k]]`, while `current = output + 8*k` uses fixed offsets.
The existing volatile-qualified pointer types and individual XOR/OR
operations are retained. The actual source patch is intentionally not made.
The existing 66 output SDs are already expanded and are outside this change.

## Actual-cost attribution and conditional savings

| Existing instructions removed/reused | Per call | Full 5,985 calls |
| --- | ---: | ---: |
| Five loop-only instructions, eight iterations | 40 | 239,400 |
| Nine dictionary-base AUIPC/ADDI pairs reduced to one | 16 | 95,760 |
| Reuse the row-ID base for tail instead of recomputing it | 5 | 29,925 |
| **Identified total** | **61** | **365,085** |

These are distinct current instructions. In the future lowering they are
removable only if the expansion adds no replacement pointer arithmetic or
spill traffic. The first row is an exact count of existing loop-only work,
not a guarantee that a future GCC binary shrinks by that amount. Constant
actual offsets 0..520 and row-ID offsets 0..16 fit RV64 immediate ranges.
Dictionary ID-dependent shift/add work remains necessary for this proposal.

Applying those identified removals without any added instructions gives:

- Current mandatory subtotal 3,460,590 -> **3,095,505**, still above 3M.
- Current whole conservative upper 3,630,058 -> **3,264,973**.
- Remaining upper shortfall: **264,973**, not 67K.

As a deliberately optimistic check, the retained scalar algorithm needs 132
word loads + 66 XORs + 65 combining ORs + nine ID loads + nine shifts + nine
dictionary address adds = **290 instructions/call**, before entry/base
setup and mismatch branching. Even replacing the current 366-instruction
comparator region by that stripped-down budget saves only 454,860 and leaves
the current mandatory subtotal at **3,005,730**, before outer control/runtime.
This is a budget argument for the specific retained nine-ID, scalar XOR/OR
layout, not an impossibility theorem for every possible software algorithm.

Thus the simple unroll/hoist proposal is useful but **does not establish the
requested full upper <=3M**. It is not authorized for a compile/reference
attempt on this evidence. Do not silently change the 3M gate, use the old
partial lower as the full budget, shorten 5,985 calls, or remove any reads.

## Semantics and future acceptance obligations

- All 528 bytes remain covered: lower guard, 64 results, upper guard. The
  final two loads are result63 at byte512 and guard at byte520; there is no
  read into padding of the ninth 64-byte dictionary block.
- All expected loads remain volatile, including the tail. OR reduction
  cannot cancel two identical nonzero differences; no success-only shortcut.
- Original failure fallback and first-error reporting remain unchanged.
- All 241,920 FP SDs, eight FP table reads per call, 35,280 mask clear SDs,
  77,175 selected mask updates, original RNG/history/CSRs/helpers remain.
- Future actual lowering would have to prove constant offsets, no extra RVV,
  no introduced stack spill/read omissions, and compute the complete CFG
  upper again. No anticipated GCC outcome is treated as an actual artifact.

First independent action: Averroes checks `compiled_audit01/RESULT.json` and
its cost terms against the unchanged current ELF. Only after that common
baseline should a further source decision be made. No alternative algorithm
or additional experimental candidate is proposed in this document.
