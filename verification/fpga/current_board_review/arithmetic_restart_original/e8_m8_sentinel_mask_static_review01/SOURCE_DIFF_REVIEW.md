# Actual Source Diff Gate

Decision: **NO_BLOCKER_ACTUAL_SOURCE_DIFF**. This permits the parent's already
authorized short C checks and one compile per backend, not reference or DUT.
Actual compiled artifact/cost acceptance remains pending.

Reviewed successor: `../full_e8_m8_sentinel_mask_software01/`.

| File | SHA256 |
| --- | --- |
| packed.h | b8322874ade95f9da7d8b6707b17780ca4e7be914d999fea699cb468251e60c5 |
| case.c | 3df39c33da95232e86edaa6e4e184fed6bfa3618a1a1cedfd0dcfb7df274be37 |
| SOURCE_PLAN.md | a11287636702bc016394a62432ef5e3926955c233fa0ccfe676a54c826b7c6c2 |

Independent read-only reverse-diff checked all 16 exact ID-zero branches and
all 16 mask memcpy offsets. Removing only those branches, their one lexical
constant, and restoring the original mask loop reproduces the old packed.h
byte-for-byte. case.c is independently byte-identical. No candidate code ran.

- Sentinel is uint64_t with UINT64_C(0x5b5b5b5b5b5b5b5b); each of the 16
  zero-ID branches reads the corresponding eight actual words. Nonzero-ID
  comparisons are unchanged. Previously verified immutable ID0 bytes justify
  this substitution; no other ID is specialized.
- raw_word remains memcpy-based, with no new typed-pointer alias/alignment UB.
  The 128 complete actual words cover offsets0..1023. Original uint16_t tail
  memcpy at offset1024 and truncated dictionary comparison are unchanged:
  last result byte and rear guard are both checked, with no read past1025.
- All 128 initializer byte writes, 16 explicit mask copies at offsets0..120,
  full three mask patterns, original per-group epochs, and out+1 helper ABI
  are preserved. No e16 upper-mask-zero assumption appears.
- Original full4095 order, seed/RNG setup, helper selection, CAP oracle,
  returned-vstart check, fallback and element/error accounting are unchanged.
  Early mismatch retains original full scalar fallback. This is not a sticky
  comparison rewrite or a skipped-read all-sentinel shortcut.

## Compiled Evidence Still Required

Only three candidate source files exist at this gate. Compiler include paths
must bind the actual new packed.h and the unchanged inherited dictionary,
operations/helper/model assets, with fixed SEW8 and prior flags. The actual ELF
must still establish vtype3/physical8, helper byte equality/no extra RVV, all
mask store coverage, tail LHU2B and correct map/stack.

Do not equate 418680 removed dictionary gold LDs with net memory reads saved.
Any literal-pool LD for sentinel construction, repeated materialization,
spills/reloads, ID loads, new joins/branches and whole-main/setup changes must
be charged. Constant materialization is a linked-code question, not determined
by one lexical C constant. Compare complete new CFG against the already audited
e8 baseline; do not rerun the old static walk or import e16 costs. Neither the
source gate nor old timeout proves a <3h execution bound.

No Host, compilation, reference, DUT, raw trace or active CSV was run/read by
this review; no production or sealed input was modified.
