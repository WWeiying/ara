# e16/m8 Single-Source Strategy Review

Verdict: NO_BLOCKER_STATIC_DESIGN_ONLY. One implementable candidate: specialize immutable dictionary ID0 in each of16 full comparator blocks and explicitly unroll the existing16-word mask copy. Not a compiled-artifact, cost, reference or DUT admission. No execution performed.

Read Zeno's m8_budget_neutral_software_audit_zeno01/REVIEW.md and STATIC_EVIDENCE.json, and actual full_e16_m8_block_unrolled01/packed.h, dictionary.h and case.c. The old comparator already returns immediately on mismatching words; it is not a per-word sticky accumulator. Do not replace it with SUB/SNEZ/OR or claim taken BEQ as a pre-proved improvement. Old source/artifacts and current tasks remain untouched.

## Sole Candidate

For each full block, load its current immutable ID once. If exactly0, compare the eight actual64-bit words, in existing order, against typed constant UINT64_C(0x005b005b005b005b). Otherwise retain the current dictionary-base and eight exact gold-word comparisons. Each mismatch returns to the original full fallback. Use one per-call local constant, no cross-call state, no adjacent-ID cache and no reuse of actual output. The seventeenth partial block remains the original independent4-byte tail at offset1024; do not read8 bytes or assume its ID is0.

Use legal memcpy for actual reads as before, not uint8-to-uint64 pointer casts. The logical output extent remains1028B even though its backing array is larger. ID0 substitution is valid only while all eight original dictionary words remain the exact typed sentinel and the frozen ID/sequence identities are retained. No dictionary regeneration or inference from observed output.

Mask change: sixteen explicit memcpy8 operations at offsets0..120 from the same immutable physical_masks[mode] into the same destination, in the same group/phase. Retain all128 bytes including the upper64 zero bytes and all16 stores. Do not combine this candidate with another shape's bitset-SB policy or an additional upper-zero specialization. No source/destination overlap, concurrent writer or MMIO semantics are introduced; these are private ordinary arrays.

## Error And Read Semantics

Keep case.c's entire fallback, returned-vstart check, helper/RNG order and counters unchanged. Passing calls must execute128 actual LD plus the4-byte tail read,528255 reads over4095 calls. On a mismatch the fast path can still stop early, exactly as before; the unchanged fallback then checks the full512-element numerical oracle and original guard expression. Do not claim129 fast-path reads after failure. Preserve the original guard-OR grouping (one guard failure report, not two), errors increment beyond the20-message limit, diagnostic order, and elements/checks increments. This distinction prevents an accidental new sticky policy or changed error count disguised as preserving all reads.

Full4095 calls,2096640 results,8190 guard expectations,4095 vstart returns and53235 helper instructions remain; fresh initialization stays128SD+SW per call. Original vtype/VRF history/gather bounds and physical mask semantics do not change.

## Cost And Later Proof Boundary

Zeno's sealed-sequence counts give52335 ID0 full blocks:418680 removable gold LD opportunities. One branch per65520 full blocks is only an illustrative dispatch debit; constant materialization, joins/jumps, nonzero paths, address setup and register allocation may add more. Mask95-to32 loop-region comparison suggests63*1575=99225 instructions, before setup and actual lowering. Neither number is actual net saving or a whole-program bound.

Future single fixed-flags artifact must count actual success paths for all source IDs and modes, including constant construction, all branch/join paths, caller/setup/ABI spills and frames, mask code and runtime. Do not subtract from old partial/core counts or assume the old frameless property survives. No automatic-vector initialization or new RVV is permitted. Preserve fixed runtime budgets; lower instruction count alone does not guarantee m8 walltime below3h.

Before any separately authorized execution, review the concrete source delta. Later bounded equivalence tests should discriminate ID0/nonzero transitions and repeated/nonadjacent IDs, first/middle/last/tail corruption and multiple simultaneous element/guard errors against the unchanged exact fallback. Successor source/ELF verification, actual lowering and cost are still pending. This review selects the single strategy; it does not authorize running tests, compiler, reference or DUT.
