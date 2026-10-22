# e64/m4 Sticky Comparator: Source-only Review

Verdict: **SOURCE_NO_BLOCKER**, limited to the exact uncompiled proposal below.
This does not authorize Host/compiler/reference/DUT execution. Current
software01 remains COST_HOLD; the parent decides the next artifact stage.

## Semantics and Accesses

With bad initialized once to0, each comparison implements
bad_next = bad OR (actual != expected), for bad in {0,1}. Therefore the final
boolean is identical to the original OR-of-XOR nonzero test for every input,
not merely correct results. A later equality cannot clear an earlier error;
two identical nonzero differences cannot cancel. The original fallback must
remain after the full comparator, as specified, not inside a per-word branch.

Eight fixed blocks cover words0..63, and the explicit tail covers64/65.
Each macro unconditionally loads actual then expected through volatile u64
pointers before the update; no bad-dependent skip or early return exists.
The Host C branch has the same semantics and still evaluates both volatile
loads after earlier mismatches. This is a source proof, not a new Host run.

Output covers exactly528B: guard at0,64 results at8..512,guard at520.
Ninth dictionary block reads only offsets0/8. Existing array element types
and8-byte alignment permit u64 reads without aliasing casts or wider accesses.
Nine IDs and ordinal0..5984 retain existing frozen-data validity obligations.
Actual RV64 LD widths/order, block addresses and absence of unexpected extra
reads still require later linked-code proof; C text alone is not that proof.

## Inline Assembly

The exact sequence is BEQ(actual,wanted,local-end), then LI(bad,1), then
local-end. Both paths fall through within the same asm statement; numeric
1f selects its own following1 label in each expansion. No asm-goto edge,
call, hardcoded register, stack adjustment, CSR, FP, vector or fence is added.

The read/write +r constraint correctly preserves incoming bad on equality.
Early-clobber is not necessary for THIS single-update sequence: both input
registers are read by BEQ before the sole possible bad write. Any register
overlap allowed by GCC must supply the same incoming values and does not
invalidate that ordering. This reasoning must not be generalized to a
future combined multiword asm that writes bad before reading later inputs;
such a change requires new constraints/review, potentially +&r.

Volatile asm prevents removal of individual updates; the memory clobber is
a compiler ordering barrier, not a hardware fence. Volatile loads are separate
full expressions on either side of each update, so all132 source reads remain
observable even after a mismatch. RV64 has no separate condition-code register
modified here. LI1 may compress, but it is skipped on equality and counted
on mismatch. No fflags oracle or new architectural side effect is introduced.

The local bad variable creates no new ABI boundary. Register allocation,
frame size, spills, pointer rematerialization and surrounding branch relaxation
remain unknown until a specifically authorized compile. The proposal is not
included by the existing executable and does not change its evidence.

## Conditional Cost Only

The independently reviewed current Spike upper is3630058, mandatory3460590.
Proposed removals are40 loop-control +16 dictionary-base +5 tail-row +65
conservatively counted comparison instructions per call:126*5985=754110.
The comparison saving uses66 XOR plus at least65 OR replaced by66 successful
BEQs; no input/output load removal or early mismatch exit is counted.

If all hoisting conditions hold without new work, the upper becomes2875948
and mandatory2706480. The124052 upper headroom is real arithmetic but NOT
measured GCC savings:20 extra instructions/call consume119700, leaving4352;
21/call would exceed3M by1633. Memory-clobber-induced rematerialization,
register moves/spills, final normalization and altered control flow must fit
inside that headroom. The existing20000 runtime allowance is retained.
The SoC baseline is higher and must not be substituted for Spike's reference
instruction gate or treated as measured simulation duration.

The direction has plausible whole-program <=3M potential, unlike unroll-only,
but no cost admission yet. A later artifact must preserve full5985/35ops,
all241920 FP stores,35280 mask clear stores,77175 selected cumulative SB,
458 original helper instructions, all132 comparator loads on both good and
bad paths, full original fallback, and zero extra RVV/CSR. Failure-path cost
is not bounded by the all-equal success projection.

Necessary future discriminators are first/middle/last mismatch with full
load-count retention, two identical differences, mismatch followed by matches,
both guards, and final result63. No such tests were run in this review.

## Identities

Baseline independent report ARTIFACT_COST_HOLD.md:
dc847e40018f8198b0fa559d1a9de2ed0b02fc388f884318873d520d65e76a15

static_sticky01/proposed_comparator.h:
d62ed3b0ad63bff1df0ba5cf78497cf3d85df309a6caa016774fdfb54edae17f

static_sticky01/PROPOSAL.md:
bf17b77491b0bc168040ee2875e4255eeb3f4cdf9d60ee2aa9add43ef920d5f8

Only this owned report was added. No production/source/ELF/old report edits,
compiler/Host/reference/DUT runs, or raw trace reads were performed.
