# Full17920 Static02 Independent Review

Verdict: **NO_BLOCKER_STATIC_DESIGN_ONLY** for proposal SHA
`a59b533385347c4f75bde74d4791b38bb1132a5acccc8da0a4488567ebe1a44d`.
The specified oracle and retained memory work agree with the selected original
parent. **Execution/budget admission remains HOLD.** This is not artifact,
compiler-cost,reference or DUT acceptance. No generation,compile,Host/Spike/VCS,
large-trace traversal,live query or budget change was performed.

Authority is the same original parent.c/scenario.S/fixtures.h pinned in static01
review. This review reread parent.c and static02 and recomputed allocation/count
arithmetic only; it did not generate17920 records or execute proposed software.
Evidence hashes and numerical checks are in review.json.

## Original State And Writes

static02:43-60 retains the original seed/op/VL/mode/sticky order and one call
per tuple:17920 calls,all2560 VL0 and all modes. It preserves512 input halfwords
per bank,128 mask bytes and130 output bytes each call,in original phase order.
The upper512 halfwords of each declared1024-element input remain BSS zero.
The proposed period caching reduces source loads,not destination stores.

For r=0..31,k=0..3,byte offset32r+8k spans exactly0..1016 once per bank.
Each64-bit store covers four little-endian halfwords,so all1024 bytes per bank
are freshly written. The16-halfword period follows original index arithmetic,
including seed/16 contributions;vf still fills B and executes its original full
vector load and scalar b[0] load. Original helpers/capacity/CSR boxing and history
are unchanged. No caller-saved pattern is assumed to survive a helper.

Output16SD at0..120 plusSH at128 covers exactly bytes0..129 with5b.
Bytes66..129 are not deleted merely because they are outside the original
post-helper result oracle. All16 mask SD likewise cover0..127 even for vm1/VL0.
Packing changes access width from the original halfword/byte loops,as explicitly
allowed by the existing packing contract;it does not preserve literal original
scalar instruction timing. No claim to Linux binary execution equivalence follows.

Implementation gates: C declarations alone do not guarantee8-byte alignment
for word arrays or byte output. Align relevant objects or use defined accesses,
then inspect actual lowering. Enforce fresh stores and helper-after-write order;
defined memcpy alone does not prove a particular instruction count. Any inline
assembly must describe memory effects and register constraints correctly. No
new RVV,FP arithmetic or CSR shortcut is permitted.

## Actual Old And Bit Oracle

Original parent.c:67 reads a[i/16] after the helper. static02:89-93,117 preserves
this as eight actual64-bit reads of a+8j. In chunk j,bit k maps to
a[4j+floor(k/16)] bit(k mod16),exactly original i=64j+k. Precomputed old or
pre-helper cached old must not replace these reads,even if correct helpers
normally leave memory unchanged. Lowering and eventual observer must prove
actual post-helper LDs; no compiler forwarding is silently accepted.

Expected W remains independently source-defined:
W[j].bit(k)=expected[op<4?op:op-4][lhs_index(seed,64j+k)]
[rhs_index(seed,64j+k,op)].bit. It must come from the pinned fixture table and
original formulas,not actual result/old memory or Spike output. M is solely
i<VL. BaseFlags is the OR of fixture flags for those active positions;sticky
is applied separately. Mode does not qualify vm1 comparisons. There is no
replacement FP engine and no canonical-tail requirement.

The Boolean proof is exact,without executing a new Host truth-table test:
- Active bit: reject A!=W,independent of O.
- Nonempty tail: A=1 is always allowed;A=0 is forbidden iff O=1 and W=1.
  Therefore bad_tail=(~A)&O&W&(~M).
- VL0: original start>=VL branch requires A=O,so bad=A XOR O.
Combining disjoint active/tail masks by OR cannot cancel errors. All operations
must remain unsigned64. A change in old is not necessarily an oracle error:
active bits ignore old,and tail W=0 allows both values. Later mutation tests
must include sensitive VL0/tail cases and these intentional non-sensitive cases,
not assert that every old-bit change must fail this data predicate.

The separate input-store integrity observer may reject unintended memory
corruption;that is supplementary and cannot replace the original dynamic-old
expression or change W/flags to match corrupted inputs.

## Reads, Guards And Exact Errors

The reconstruction at static02:112-128 is correct. Eight LDs cover output0..63;
the final unsigned LHU covers64..65. For chunk j,
`previous>>8 | ((next&255)<<56)` yields bytes8j+1..8j+8. The final chunk thus
includes result byte64/bit511,not guard65. Leading guard is byte0;after the
zero-extended final LHU,previous>>8 is exactly trailing guard65. No out-of-array
read,misaligned output+1 cast,shift-by64 or stale upper bits is needed.

Every chunk is read after an earlier mismatch. The loop bad&=(bad-1) removes
one invalid bit per iteration and increments errors once,so two bad bits in
one byte add2 and equal errors in different words cannot cancel. No Zbb is
assumed. Per original parent.c:61,85-87,low32 status contributes at most1,
flags mismatch contributes1,and either/both bad guards together contribute1.
The actual low-status check must precede bits,as static02:136 explicitly states;
the separately printed kernel is not a license to reorder diagnostics.

Preserve prior,errors,cases and `errors!=prior && details++<20` literally in
meaning: details increments on every erroneous call,including after20,but not
on passing calls. Exact DETAIL fields/error deltas and final exit condition
remain. Maximum original total17920*(512+3)=9228800 fits unsigned32.

## Layout And Cost Claims

The allocation arithmetic is correct:W20480+M448+flags2240+periods1536+
fixtures12320+BSS4354+runtime8192+stack65536+text65536=180642B. Actual alignment,
linker stack-top16-byte subtraction,metadata and stack depth are not proved.
This is ample planned1MiB space,not a produced map.

The proposed literal schedule's incomplete floor is correctly6254083:
5178880 fresh stores+161280 output/guard loads+143360 old loads+
286720 W/M loads+143360 period loads+340480 helper instructions+capacity3.
This is conditional on this schedule's all8 period and W/M reads per call;
it is not a universal lower bound for every possible scalar optimization.
The older5680643 lower bound still applies to retained fresh scalar writes.

The allowances sum728/call;adding272/call and250000 fixed gives18170000.
The report correctly labels this a planning envelope,not a certified upper.
Nonblocking accounting clarification:24 reconstruction shifts/OR omit the
eight `next&255` masks as a named item;these must be charged within the39
other/control allowance or explicitly itemized later. The all-correct paths,
prologue/spill/address costs and finite fixed reserve have no linked CFG proof.
Likewise four instructions per bad bit is only a plausible scalar idiom:
36700160 extra instructions is illustrative,not an error-path bound against
compiler spills or diagnostics. No automatic timeout can be derived from it.

At existing700's observed478.32067 retires/s,the planning value corresponds to
10.55196h and schedule floor to3.63197h. These are different-mix projections,
not new measurements,hardware walltime bounds or permitted budgets. No3M or
<=3h admission follows. Existing ceilings are unchanged.

## Decision Boundary

No blocking source-level contradiction found in this exact static proposal.
Before any separately authorized implementation admission: independently
derive full W/M/flags/period tables from original source;prove every call's
freshness/old reads and helper bytes;check all invalid-bit/guard/detail
semantics;and inspect actual alignment,scalar lowering,CFG and runtime bounds.
No arbitrary subset or short prefix closes17920. This review grants none of
those execution stages and does not change accepted700 or original Linux scope.
