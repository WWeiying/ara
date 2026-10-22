# Full17920 Independent Static Review

Verdict: **NO_BLOCKER_STATIC_FEASIBILITY** for the report's bounded conclusion:
full source portability/layout is plausible,not prepared or accepted;
the existing3M instruction gate cannot be met under retained scalar fresh
writes,and completion within3h is unproved. **Execution remains HOLD.**
No compile,Host/Spike/VCS execution,large-trace scan,live query or budget change.
Only original source,existing small evidence and static arithmetic were read.

Reviewed report SHA:
`924576c7e1bf1ccb21a32c7b0fc6b5f00de028cd383fb29c5667bc676e8548b4`.
All evidence hashes and derived counts are in review.json. This verdict is not
an implementation/worker gate or a claim that original Linux failures closed.

## Source Identity And Complete Scope

Original files reside in
`../prepared02/prepared/alias_v8_e16m8_prefix682/original/`.
The directory name does not truncate parent.c. Fresh hashes of archived
`rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8` and retained
`original_rebuilt.elf` both equal
`266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
The recorded original rebuild command selects SEW16,UNMASKED1,RESTART0,
UNBOXED0,DESTINATION_KIND1. No reconstruction/compiler rerun was performed.

parent.c:39-44 establishes seed32/op10/VL7/mode4/sticky2/trial1,all17920 calls
in that order. Lengths are0,1,2,3,256,511,512;2560 VL0 calls remain.
Each op appears1792 times:7168 vv and10752 vf. Complete observations are
9175040 result bits,35840 guard bytes,17920 flags and17920 returned-vstart.
There is no RNG state: parent.c:33-36 defines deterministic input indices.
The seed/operation transition and prior vector/CSR history still must remain.

scenario.S has capacity3,four16-instruction vv and six21-instruction vf helpers:
193 static instructions and340480 dynamic helper instructions plus capacity3.
All helpers save/restore fflags,load both full512-halfword sources and64-byte
mask,apply requestedVL/sticky,read vstart/fflags,and store64 result bytes.
The nonrestart helpers do not install an artificial vstart write. Each vf keeps
its full B load as well as LHU b[0],boxing and fmv.d.x. No helper substitution,
extra RVV,VL0 skip or mode skip is permissible.

## Freshness And Oracle

parent.c:49-55 rewrites128 mask bytes,then512 a/b halfwords each,then130 output
bytes before every call,including VL0 and unchanged tuples. Upper512 halfwords
of each1024-element source array remain original BSS zero. Source-derived
scalar packing may widen writes,as accepted prefix packing already does,but
must retain all written bytes and original mask/input/output phase order.
No ROM-pointer replacement or cross-call write elision is equivalent here.

fixtures.h contains1536 pairs,bit in{0,1},flags in{0,16}. Static inspection of
the initializer confirms EQ/NE NV for sNaN(index15),and ordered comparisons
for either qNaN(index14) or sNaN. The source fixtures,not a new host floating
point engine or observed Spike payload,are the oracle.

parent.c:61-88 agrees with the report's sets:VL0 preserves old;active gets the
single fixture bit;nonempty tail allows{old,1,wanted}. Because vm1/start0,
masked-inactive and prestart branches do not apply. Flags are exact
sticky OR fixture flags from i<VL only,independent of the loaded mask mode.
Output[0] and[65] are guards. Bytes66..129 must be initialized but are not
additional post-helper result checks in the original source.

Implementation condition: parent.c:67 reads old from **post-helper memory**
`a[i/16]`,not from an observed VRF result or immutable reference row. Valid
helpers do not write that memory,but a new oracle should retain the64-byte
post-helper old read,or explicitly establish the invariant used to replace it.
Otherwise input-memory corruption could change equivalence with the original
failure oracle. Static01's table is correct when its old operand retains this
meaning; no current implementation is accepted by this review.

For each word,let A=actual result,O=observed old,W=fixture wanted bits,
M=active mask. VL0 rejects A XOR O. For VL>0 the exact invalid-bit vector is
`((A ^ W) & M) | (~A & O & W & ~M)` within the512-bit result domain.
This follows because tail0 is invalid only when both O and W are1.
Two must-zero/must-one masks also encode the sets exactly. Do not choose one
canonical tail or XOR errors from different words together.

Original errors increment per invalid bit,once for nonzero low32 status,
once for wrong flags and once for either/both bad guards. Preserve prior/errors,
cases and the first20 DETAIL policy(parent.c:89-100). Old packed byte-error
counts are insufficient for exact diagnostics. Error-only original per-bit
fallback or exact invalid-bit popcount can preserve totals;fallback must not
double-count status/flags/guards. All result words are read even after an error.

## Layout And Cost

The report's2240 `(seed,op,VLslot)` entries can share mode/sticky-independent
oracle storage without dropping any calls. Its allocation adds to420322B;
after8192B runtime reserve and65536B code reserve,the arithmetic remainder is
554526B of1MiB. The existing replay.ld also subtracts16 from stack top and
requires64KiB stack clearance. Alignment,actual code/data,BSS and call-stack
depth remain linked-artifact obligations;this is not an actual map proof.

Independent floor recomputation:
4587520 fresh input stores +286720 mask stores +304640 output stores
+161280 result/guard loads +340480 original helper instructions +3 capacity
=**5680643**. This assumes at most8B per scalar store and best packing;even
the4587520 input stores alone exceed3M. The unchanged full-row input copies
plus16 expected LD/call raise the incomplete subtotal to10554883. Neither
number includes all control,addressing,oracle operations or runtime work.
Retaining post-helper old reads adds up to143360 LD across the full program,
also absent from the optimistic floor. This omission does not invalidate a
lower bound;it must not be mistaken for a complete implementation estimate.

Existing700 terminal metadata actually records child0/4549.983158s and
2176351 retires;its reference HANDOFF records2179709 firmware. The report's
478.32067 retires/s,55.80055M scaled firmware,32.35544h scaled runtime and
3.29895h floor-at-that-rate calculations are correct. They are cross-mix
proxies,not full17920 timing measurements or a hardware walltime lower bound.
The floor alone needs525.985 retires/s to fit3h before omitted work.

## Permitted Scalar Reduction Directions

1. Exploit16-halfword input periodicity. Load four packed64-bit A words and
   four B words per vv call;vf B can reuse one replicated word. Repeat the
   stores over all128 words of each mutable source,without skipping a call.
   This can reduce input ROM LD from4587520 to111104 across all calls before
   setup/spill costs,while all4587520 destination SD remain. Do not carry
   mutable observer state between calls or reorder across source phases.
2. Use bounded scalar unrolling/address blocks,16 SD mask fills and16 SD+SH
   output fills. Preserve each mode's FF/AA/24/00 and all130 output bytes.
   Fixed-size memcpy or equivalent defined accesses need later actual lowering
   proof;C source alone cannot promise no byte loop,spill or extra RVV.
3. Share only immutable fixture patterns/flags and VL masks. W repeats every
   16 result bits for this source;old aliases have a different256-bit period.
   Retain actual old observation and exact allowed-set logic. Eight aligned
   output LD plus LHU at64 cover bytes0..65;explicit shifts must keep both
   guards and all512 result bits without unaligned output+1 casts.
4. Use noncancelling mismatch accumulation and an exact error-only fallback;
   keep original full oracle reads,flags checks,DETAIL accounting and all
   predecessors. Do not hoist fresh stores out of nested loops or partition.

These directions reduce overhead above the proven floor;none can make the
retained scalar-write scope fit3M. Any subsequent cost/implementation proposal
needs separate authorization and actual lowering evidence. This review does
not approve changed budgets,new compilation,reference or DUT execution.
