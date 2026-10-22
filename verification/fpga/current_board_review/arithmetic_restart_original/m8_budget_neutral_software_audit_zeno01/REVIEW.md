# e16/m8 Budget-neutral Software Overhead Audit

Status: concrete static opportunities; no implementation or execution.
No budget change, Host, compile, reference/DUT run, raw scan or live-task query.
Old linked source/ELF and all sealed evidence remain untouched.

## Actual Linked Baseline

Source: A/full_e16_m8_block_unrolled01/case.c, packed.h, dictionary.h.
Actual soc/compile.log.command.json links that case.c, original/scenario.S
and soc/main.c at -O2 with tree/SLP auto-vectorization disabled.
SoC ELF SHA:
f70831da5a87b07ff0c14852d4d38968226a35653a7568b775577b0a07948923.
The inspected comparator/mask instruction encodings were byte-matched to
this linked ELF, not inferred from source alone.

Accepted reference READY metadata records2807400 firmware instructions.
That is a prior actual reference count, not a new measurement. Its8339.431s
20percent-margin scalar projection is not a3h DUT guarantee.
This audit does not query or reinterpret any current m8 simulation state.

Full contract remains4095 original continuous calls,2096640 results,
8190 typed guards,4095 vstart returns,53235 original helper instructions.
Every call keeps128 SD plus one4B SW fresh initialization and128 real LD
plus one4B LW output reads:1028B,528255 actual reads overall.
Typed16 sentinel005b and final32-bit005b005b must not become5b byte fill.
All original RNG/history/helper order/gather bounds and slow error totals stay.

## Findings from Actual Source and ASM

1. Comparator is already mostly optimal per word.
   packed_mismatch.constprop.0 PC8000007a..800006d4 is frameless.
   Its main body has128 expected LD +128 actual LD and128 equality branches:
   first BEQ, then127 BNE early-fallback branches. There is no perword
   SUB/SNEZ/OR accumulation. Only the final4B LW pair at800006c4/800006cc
   uses SUB800006ce and SNEZ800006d0. The all-equal static path is451
   instructions/call. Merely swapping BNE for sticky BEQ/LI cannot be claimed
   to reduce pass-path word comparison cost; taken-branch behavior may worsen.

2. Expected values are unnecessarily reloaded when dictionary IDs repeat.
   All16 full blocks independently LHU their ID, shift/add its base and
   reload8 immutable expected words. The actual output reads must remain;
   only immutable expected-side loads/address calculations are candidates.
   Existing sequence.json, not regenerated gold, contains65520 full blocks.
   It has48655 adjacent-ID hits and52335 uses of ID0. dictionary.h confirms
   ID0's eight words are all005b005b005b005b. Final partial block17 must remain
   a separate4B check; never use padded dictionary bytes as actual output.

3. Mask setup still has a small scalar copy loop, not bitset RMW.
   packed.h:133 copies16 immutable64-bit mask words. Actual PCs80000b38..b44
   repeatedly execute source LD/source ADDI, SD, end-address ADDI,
   destination ADDI and BNE. Including its entry jump, the loop region costs
   95 instructions/group:16SD+15LD+15sourceADDI+16endADDI+16destADDI+16BNE+1J.
   There is NO business-mask LBU/ORI/SB sequence to optimize away.
   All1575 groups write full128B; CAP512 uses64B, upper64B remains zero.
   This is25ops/4095 history, not the FP shapes'2205 mask groups.

4. Fresh output initialization is already unrolled; the comparator has no
   repeated stack frame. Main's320B frame is entered once, not4095 times.
   Do not advertise deleting those one-time saves as a large percall saving.
   There are genuine percall address costs: a/b/out/mask AUIPC+ADDI setup at
   80000d6e..d8a, checks address/reload before comparator80000d92..d9e, and
   checks address after it80000db2..dbc. Register reuse may help but is a
   secondary hypothesis: caller-saved values are clobbered by existing
   helpers/comparator, and forcing new callee-saved state may add spills.

## Comparison to Later Actual m4 Implementations

e64/m4 software02/packed_output.h uses sticky BEQ/LI but still loads each
expected word. Its main advantage here is completing all reads after a
mismatch, not automatic pass-path speedup over old BNE.

e32/m4 software02/packed_cache.h uses a real8-u64 expected-register cache:
first block unconditional fill, subsequent ID-tag checks, sticky all-word
comparisons and a separate last partial block. Its actual SoC asm at
8000007a starts with eight gold LDs and contains tag BEQ branches at8000010a
and80000186; this comparator is also frameless. This proves the strategy
can lower without a cache frame in that shape, not that e16/m8 lowering,
spill behavior or cycle cost is already proved.

## Narrow Falsifiable Proposals, Not Implementations

Priority1: specialize immutable sentinel block ID0, retaining actual reads.
One correctly typed sentinel GPR percall can replace its eight gold LDs per
hit, while every actual LD/comparison still executes. Keep nonzero-ID blocks
on the existing exact path and final4B tail separate. Reset the constant/
dispatch state percall; no reuse of prior output, no prefill from gold.
Existing table gives an opportunity to eliminate418680 gold LDs; adding one
dispatch branch/full block costs65520.353160 is thus only preliminary
headroom before constant setup, branch joins, register spills and other
code-generation costs, NOT measured net savings or a firmware upper bound.
Prefer this one-constant path over eight-register caching if its actual
future CFG is smaller. No new dictionary/gold generation is needed to
formulate the hypothesis, but later equality/UB proof remains mandatory.

Alternative: adapt the mature eight-word adjacent-ID register cache.
48655 hits could remove389240 gold LDs, before61425 tag tests, tag moves,
branch joins or spills. The existing m4 shows frameless lowering is possible;
do not invent an obligatory65520 save/restore cost, or assume zero overhead
on m8. The JSON's65520 term is explicitly an illustrative worst allocation
cost, not a measured e16 frame. Choose one design after authorized static
CFG proof, not repeatedly compile parameter variants.

Priority2: unroll the existing16-word mask copy.
Keep all16 stores at offsets0..120 in the same group/phase and full bytes.
Straight16LD+16SD is32 instructions before setup, versus old95 loop-region
instructions;63*1575=99225 is directional headroom, not net compiled saving.
Literal zero for the immutable upper64B may remove more gold-table LDs
without removing mask stores. Do not replace this accepted final-mask-copy
contract with another shape's original bitset-SB policy.

Sticky comparison is an optional correctness form to keep EVERY actual read
even after an early mismatch; by itself it is not the optimization claim.
After latched mismatch, run the original complete element/guard fallback
once so errors count original failing elements/guards, not failing blocks,
and first20 diagnostics/source counters remain unchanged. No checksum,
current-value caching, extra RVV or helper/reset shortcut is allowed.

## Evidence Needed to Falsify or Accept Later

This is not permission to run these steps now. Upon separate authorization,
accept a successor only if actual linked CFG preserves all4095 history,
128SD+SW freshness,128LD+LW actual reads, helpers/ABI/CSR and original errors;
IDs0/nonzero transitions, nextseed, repeated/nonadjacent IDs, high-byte and
tail/guard corruption must discriminate wrong-cache/tag/data behavior.
Compiler output must show the intended gold-load reduction WITHOUT
unexpected actual-load elimination, new RVV, alias UB or spill growth.
Count the real success-path CFG including dispatch/frame/address terms;
the existing table statistics alone are not that count.

Even proven software instruction savings do not prove wall time<3h:
the full m8 vector/memory work and backend latency remain unchanged, while
new branches/code size may affect timing. Existing budget stays fixed.
If later exact proof does not fit it, report the insufficiency, not a blind
timeout run, reduced calls or unauthorized time extension.

STATIC_EVIDENCE.json pins the actual sources/asm/ELF and stores all ID/mask
counts. No SUB/SNEZ/OR-perword or large percall-frame claim is supported.
