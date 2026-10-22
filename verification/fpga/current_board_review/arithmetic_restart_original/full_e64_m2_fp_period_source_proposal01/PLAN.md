# One FP8 Period Source Proposal

Static proposal only. No second Host, compilation, Spike, VCS or RTL change.
The sealed full_e64_m2_block_software01 remains COST_HOLD3074202.
Hilbert completed its actual artifact review before this proposal was written:
../full_e64_m2_software_review01/REVIEW.json,
SHA11c7243bec81ff15789ffc73339ca107af9ae15b9bcbf3db42db22b33fd7b048,
NO_BLOCKER_SOFTWARE_ARTIFACT_REVIEW_BUDGET_HOLD.

## Single Source Delta

case_proposal.c replaces only the original op>=25 FP refresh loop with
refresh_fp_period(a,b,fp_inputs,seed), and adds fp_period.h.
Reversing those two changes is byte-identical to sealed software01/case.c.
It does not alter any mask, output, dictionary, fallback, helper, RNG or loop.
Headers already belonging to software01 are intentionally not copied here:
this directory is a proposal, not a runnable firmware or reference entry.

fp_period.h makes eight fresh volatile uint64 table reads INSIDE each call,
then dispatches seed0/1/2 to a fixed unrolled64-store list. Every i0..31 writes
a[i] followed by b[i], including VL0, start>=VL and equal previous input values.
Each8B builtin memcpy is followed by an empty compiler memory barrier to
preserve store sequence/no-elision. These barriers emit no hardware fence.
No FP arithmetic, hostfloat, CSR access, extra vector instruction or checksum.
The added volatile reads observe the original immutable fp_inputs bit table;
they prevent constant materialization/cache hoisting across calls. No cached
input values are carried between calls or seeds. They are not volatile writes
to any new architectural CSR. Destination arrays are disjoint from the table.

The original repeated64 table reads may become eight reads; the table is const,
nonaliasing and immutable. All64 DESTINATION writes remain, exactly ordered.
This proposal changes pure scalar table-load count, not fresh input writes.

## Algebra and Full Scope

For i=8q+j, (i+seed)%8=(j+seed)%8 and
(3*i+seed)%8=(3*j+seed)%8. Thus four8-element periods exactly reproduce
both original input arrays for all three original seeds without modulo/index.
STATIC_PROOF.json enumerates every original versus proposed destination/index
tuple for3*64 stores and verifies literal header order.

Full5985/35ops/1890FPcalls remains; FP destinations120960 u64 writes total.
CAP32/physical2full256B/output272B34wordfresh and two u64 guards0x5b remain.
Original mask per-group128B clearing and bit construction remain. The fifth
gold64B block still has only16 valid bytes, with no padded read. The original
640 FP64 expected words/5120B ELF bit identity and eight original input words
are borrowed unchanged from the sealed artifact. Original fallback, seed
RNG and all helper/CSR history remain. No flags oracle/reset is added.

## Constructive Cost Proof, NOT Actual GCC Evidence

Sealed actual linked CFG gives FP setup+return11 plus32*15 loop instructions:
491 per FP call,927990 across1890 calls. Do not use an assumed492 count.
lowering_witness.S is an UNASSEMBLED scalar instruction-list proof, not another
trial implementation: eight LD, at most five seed-selection instructions,
64 SD in exact source order and one return give at most78 leaf instructions.
All SD offsets0..248 fit immediate range; case branches fit direct branch
range. No loop, modulo, FP/vector/CSR/fence or callee-saved register mutation.
The witness uses only ABI caller-saved scratch registers.

Allow50 instructions for call, argument/address formation and caller spills:
at most16 integer caller-saved registers need32 SD/LD, two stack adjustments,
up to16 other address/move/call instructions. Constructive phase upper128.
Constructive saving (491-128)*1890=686070, comfortably above75000.
If all other CFG costs stayed unchanged, old upper3074202 would become2388132.
This proves a cheap scalar lowering exists; it does NOT prove GCC will emit
that lowering for fp_period.h, nor that its other register allocation is unchanged.
Actual new GCC count remains null. Do not release HOLD using this arithmetic.

Future actual-compile admission requires complete per-PC CFG delta including
changed main spills/setup: NET saving>=75000 and whole positive-path bound<=3M.
Equivalently, when other costs are unchanged, new FP phase<=451 per call
would save75600 and give2998602; the128 witness has substantial design margin.
Changes outside the FP phase must be accounted, not assumed free. Gate remains
3000000, without timeout extension or a reference trial to find its true cost.

## Future Checks, Not Executed

An authorized successor Host should compare original versus unrolled all5985
positions/counters/diagnostics and128B dirty-mask footprint. Receipts must
check exact64-store a/b sequence per call, not just final values. Delete one
equal-value write in each bank, stale-cache across seed, reordered/duplicated
store and missing refresh at VL0 must reject. Preserve all prior guard/result/
vstart/UB/PROT_NONE negatives. Actual GCC inspection must prove all64 SD sites
execute on every FP call, direct5120B FP identity, no extraRVV/fence and stack.
No such Host or compile stage is authorized by this static proposal.

INITIAL_STATIC_COUNT_CAUSE.json preserves the first source-audit failure:
the assumed old setup count12 was corrected to the actual pinned count11.
No oracle, sealed artifact or firmware execution changed; successor static
source/assembly-list audit exited0. This was not a Host/RTL failure.
