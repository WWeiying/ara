# e32/m2 Scalar Setup Candidate

Status: STATIC_SOURCE_CANDIDATE_ONLY_NOT_COMPILED. This is one candidate,
with two separately justified scalar setup changes. No Host, compiler, Spike,
DUT, RTL edits, live query or background observation. The original static
COST_HOLD and all sealed predecessors remain unchanged.

## Files And Integration

scalar_setup.h contains the proposed implementation. candidate_original.c is
an exact static integration against recovery22/reconstructed_oracle.c;
original_integration.patch is the read-only diff. It still has the original
Linux syscall/startup interface and unoptimized per-element oracle: it is NOT
a ready bare-metal firmware and must not be run as a SoC image.

The diff adds an e32/CAP64 qualification, an8-word seed cache, and replaces
only the mask setup and FP refresh loops. It does not change original RNG,
op/seed/VL/mask/start iteration, helper calls, output initialization, fallback
or checks. The failure function and the entire suffix from the original
functions[op] call through oracle/exit are byte-identical in source.
The separate previously proposed264B packed positive oracle is not implemented
here; its full original mismatch fallback remains a future integration duty.

## FP: Preserve128 Ordered Writes Every Call

After the original64-step RNG and all integer overrides for each seed, compute
q[k]=fp_inputs[(seed+k)%8], k=0..7. This reads the original8 fixed uint32
patterns and writes only a new32B local cache. It never writes a/b or changes
RNG state. It is recomputed for each of the3 seeds.

For i=8j+k, original a[i]=fp_inputs[(seed+i)%8]=q[k].
Original b[i]=fp_inputs[(seed+3i)%8]=q[(3k)%8].
B cache-index order is0,3,6,1,4,7,2,5. This is equality of integer bit patterns,
including signed zero/NaN representations, not host floating computation.

The original op>=25 branch remains inside EVERY trial, before output fill
and helper. e32m2_refresh_fp expands i=0..63 in order; each pair is
a[i] assignment, compiler barrier, b[i] assignment, compiler barrier.
Thus source events remain a0,b0,...,a63,b63,128 uint32 writes, for every one
of1890 calls, including VL0, duplicate starts, no-op and identical-old inputs.
There are241920 required writes. No call is deduplicated or refresh hoisted.
Integer calls do not invoke this refresh. The next seed still executes its
original RNG writes before any integer operation.

The barrier is __asm__ __volatile__("" ::: "memory") after EACH store, not
only after a pair or block. It has an empty template, not a RISC-V fence.
Its purpose is to prevent combination/reordering/deletion across observable
compiler memory boundaries. This source mechanism is NOT a substitute for
later checking actual128 SW, exact a/b order, no SD merge and no extra RVV.

## Mask: Preserve Every Cumulative Selected Bitset

e32m2_initialize_mask first performs16 exact8B zero memcpy operations covering
offsets0..127 once, each followed by the empty memory barrier. It then chooses
one mode branch and expands every original selected index in increasing order:

- mode0:0..63,64 cumulative byte RMW assignments.
- mode1:1,3,...,63,32 cumulative byte RMW assignments.
- mode2:2,9,16,23,30,37,44,51,58,9 cumulative byte RMW assignments.

Each expression is the original byte update
mask[i/8]=(uint8_t)(mask[i/8] | (1u<<(i%8))), followed by a memory barrier.
It is not one final byte write, not an OR of a precomputed full mask, and not a
copy of final128B. With an initially zero byte, induction over the ascending
index list proves every intermediate store value and address equals the
original selected loop. The barrier also separates successive updates to the
same byte. Upper120 bytes stay zero because all selected indices are<64.
All2205 groups retain full zeroing before any selected update. There are735
groups of each mode, hence(64+32+9)*735=77175 required selected SB events.
For an out-of-contract mode other than0/1/2 the function clears only, matching
the original selected predicate; the actual source only uses0..2.

This is a distinct second scalar optimization, not silently included in the
FP claim. Its savings come only from removing index/predicate/loop control,
not from removing the original bitset evidence. The zeroing uses the already
reviewed exact16x8B memcpy idiom; later actual code must prove full coverage,
correct sizes and completion before the first bitset. No zeroing is skipped
merely because the previous group's final bytes match.

## Defined Behavior And Footprint

SEW32 is compile-time qualified; CAP64 is runtime qualified before specialized
setup. Original word is uint32_t. FP pointers are actual uint32 arrays;
q has8 uint32 entries. No restrict, alias-punning, float conversion or altered
alignment promise is introduced. Each a/b offset is4*i in0..252; each access
is4B and fits the required256B prefix of the unchanged4096B backing.
The q read indices are in0..7. Largest compile-time3*i is189, no overflow.
seed+k is at most9; even general unsigned arithmetic is defined.

Mask loads/stores use uint8_t. Shift counts are0..7 of UINT32_C(1), never32
or64. Zeroing uses memcpy and supports byte alignment without casting the
destination to uint64_t*. Its16 spans exactly tile128B. No access to output
is added by these helpers, and no neighboring backing/guard is touched.
Do not add -ffast-math, alias assumptions, vectorization, or flag changes.
Future build must retain the same RISC-V GCC and disabled tree/SLP RVV
vectorization as the reviewed scalar harness.

## Static Cost Hypothesis, Not An Admission Bound

Prior comparable-lowering estimate was4432804 instructions, based on actual
m1 CFG scaled toCAP64, not a measured m2 program. It includes1814400 for the
15-instruction FP loop and1347255 for mask predicate/bitset work; output
33 SD/33 full LD and comparisons were already included.

Do NOT assume the8 cache words remain in registers across memory clobbers.
Budget one LW plus one SW for each of128 assignments:256 instructions/call.
Allow32 more/call for base/setup/spill overhead as a planning hypothesis:
1890*288=544320. q preparation occurs only3 times; reserve192 instructions.
Actual compiler output may exceed this hypothesis and must be inspected.

Every selected mask update can lower to LBU/ORI/SB with fixed immediates:
77175*3=231525, plus up to6 dispatch/control instructions/group gives244755.
The16 zeroSD/address work stays in the old baseline and is not subtracted.
This comparison is against the old bitset/predicate component only.
For the later5-block dictionary reserve8 addressing/ID instructions/block/
call:239400, with all33 original output word comparisons still mandatory.

Combined illustrative estimate:
4432804-1814400-1347255+544320+192+244755+239400=2299816.
Adding an explicitly unproven250000 instruction planning allowance gives
2549816. These are neither actual CFG counts nor conservative mathematical
upper bounds. The point is a source-based, falsifiable saving hypothesis with
room for dictionary costs, not a new COSTPASS or authority to run.
The cache/FP and mask changes must be measured separately in later disassembly
so unsuccessful lowering cannot hide behind this combined number.

## Code And Stack Tradeoff

Full expansion creates128 FP store expressions. With one LW/SW each and
32 setup instructions the FP path estimate is288*4=1152 code bytes before
compression. All three mask arms together have105 updates;3 instructions
each give1260B, plus roughly24 clear/address instructions96B and dispatch.
The old FP loop was15 instructions; old mask control was a small reused loop.
Plan roughly2-4KiB extra text, NOT a measured text delta or allocation bound.
There is no added target-data table beyond32B cache. No128-value stack array.

Actual register allocation might reload/spill cache and caller state because
of the barriers. The existing64KiB reserved stack and dictionary memory plan
have ample planning space, but future actual map/frame inspection is required.
No tail guard/oracle may be sacrificed to compensate for text or spill growth.

## Unchanged Acceptance Obligations

Full5985/35ops/3 seeds,383040 results,11970 uint32 guards,5985 vstart returns,
77805 original helper instructions, original640 FP bit patterns, original
integer seed assignments552 and original helper machine bytes all remain.
264B is33 whole8B reads/stores; the final8B is element63 plus rear guard.
Physical group2 must join full256B. Mask software128B/actual vlm8B differ.
Source b[3]=32 is valid atCAP64; retain CAP64 gather/slide/reduction/compress
gold and full history. No fflags result oracle is added or claimed.

Before any future Hostcompile authorization: independent exact source review.
Later Host negatives must delete any FP store even when old bytes match,
swap a/b or index order, merge two stores, omit a same-byte cumulative SB,
move a bitset ahead of final clear, and corrupt upper mask/last output word.
Full original C equality and fallback checks remain, not a prefix substitute.
Before reference: actual compile must prove exact write widths/order/counts,
no runtime modulo/FP refresh loop, no extra RVV/fence, full actual oracle,
map/stack and complete CFG <=3M. If this concrete lowering hypothesis fails,
preserve evidence and reassess statically; no blind variants or long trial.
