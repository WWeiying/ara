# Selected FP Parent17920: Static Feasibility

2026-10-14. Source/assembly and existing small reports only. No table/model
generation, compiler, Host, reference, DUT, large-trace traversal or live query.
No producer/accepted input was changed. This is a whole-parent proposal, not
acceptance, a compiled-cost claim, or permission to extend any running budget.

## Inventory And Identity

The existing FP directory has original provenance/rebuilt-parent evidence,
50/130/265/682/700 preparation and scoped acceptance. Its
[fp682_cost_feasibility01.md](fp682_cost_feasibility01.md) analyzes the old
unpacked682, while [packed HANDOFF](full682_packed_prepare01/HANDOFF.md) and
[700 HANDOFF](full700_m9_prepare01/HANDOFF.md) supersede that implementation's
cost. No full17920 feasibility/preparation artifact was identified in the
reviewed FP document inventory. This note adds only the full-scope memory and
mandatory-work analysis; it does not repeat those original identity proofs.

Selected original: rvv_fp_compare_unmasked_alias_v8_e16_m8, archived ELF
/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8,
recorded SHA266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754.
Full restored source/helper/fixtures are in
prepared02/prepared/alias_v8_e16m8_prefix682/original/{parent.c,scenario.S,fixtures.h}.
parent.c SHA3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c
and helper SHAeb5659c77622636492675c2ffd77b2e1a2fc93ede9471013d123f54151a02f86
have existing byte-equivalent original-ELF provenance. This directory's name
does not truncate its original/parent.c. See [mapping](prefix700_static_review01/REVIEW.md).

## Exact Whole Scope And State

- SEW16/M8/CAP512, physical v8..15 and v16..23; destination v8 aliases lhs.
  UNMASKED=1, RESTART=0, boxed scalar. Not a masked/restart/unboxed variant.
- Original order: seed32 -> op10 -> VL7 -> mode4 -> sticky2 -> trial1.
  Total17920, with no selection filter; lengths0,1,2,3,256,511,512.
 2560 VL0 calls remain; every op has1792 calls. There are7168 vv and10752 vf.
- Full oracle:9,175,040 result bits;35,840 guards;17,920 returned-vstart and
 17,920 exact returned-fflags checks. The full sequence has340,480 dynamic
 helper instructions plus capacity3, not700's12,880. Static helper bytes:
 capacity3 + four16-instruction vv + six21-instruction vf =193 instructions.
- No mutable PRNG exists here. The source formulas are
 lhs=(i+seed+7*(seed/16))%16 and rhs=(3*i+5*seed+seed/16)%16 for vv;
 vf rhs=seed%16. Preserve the original32-seed order, not a made-up RNG stream.
- Each helper saves fflags, sets capacity, loads both full512-halfword vectors
 and logical64-byte mask, selects requestedVL, installs sticky, executes the
 comparison, reads vstart then fflags, restores saved fflags, restores capacity,
 and stores64 mask-result bytes. vf additionally LHU-loads b[0], boxes with all
 upper bits1 and fmv.d.x. Even vf retains the original full b-vector load.
 No partition reset, replacement helper, extra RVV, or skipped VL0/mode is legal.

## Fresh Inputs Are Per Call, Not Readonly Reuse

parent.c initializes ALL128 mask bytes, then all512 halfwords of BOTH a and b,
then ALL130 output bytes before EVERY helper. a/b are declared1024 halfwords
each: only their lower512 are rewritten; upper halves retain original BSS zeros.
The output sentinel is byte0x5b. Guards are output[0] and output[65]; bytes66..129
are initialized but not post-helper checked by this original oracle. Do not
silently omit their initialization or invent a stronger tail-result requirement.

The accepted packed implementation's five prefix-specific input ROM rows are
storage sharing only: its runtime still performs128 64-bit copies into each
input every call. Full17920 must similarly write36,700,160 input bytes,
2,293,760 mask bytes and2,329,600 output bytes. ROM pointers cannot replace
mutable a/b, and equal input values across consecutive calls do not permit
skipping writes. Literal original halfword-store granularity is not required
by the accepted packing precedent, but all bytes and pre-helper freshness are.

For the full source there are at most48 distinct1024-byte input rows:16 lhs
rotations,16 stride3 rhs rotations and16 scalar-constant rhs rows. This is a
formula-derived bound, not a generated/deduplicated full table. A much smaller
16-halfword periodic representation is possible, but it can only reduce ROM
and load/address work, never the required fresh destination writes.

## Exact Packed Oracle, Not One Spike Result

Original expected[6][16][16] supplies result bit and flags. For this selected
unmasked/vstart0 parent, the allowed set per bit is exactly:

| Position | Allowed values |
| --- | --- |
| VL0, every bit | old alias bit from a[i/16] at bit i%16 |
| VL>0, i<VL | fixture bit only |
| VL>0, i>=VL | union of old alias bit,1,fixture bit |

ModeFF/AA/24/00 does NOT predicate the comparison (vm=1), but full mask writes
and vlm still occur. The original masked-inactive agnostic branch is unreachable
for this parent; do not import its rule or mask off NV. Flags are sticky OR all
fixture flags for i<VL only; tail NaNs cannot contribute. Helpers' actual
save/restore and immediate CSR reads remain independent obligations.

Two64-byte must-zero/must-one masks preserve every allowed set, including mixed
tail choices. Reject if (actual & must_zero) OR (~actual & must_one) is nonzero;
this is not XOR accumulation across words, a checksum, or one chosen canonical
tail. All64 actual bytes and both guards must be read. No short-circuit may
skip later result words. With an aligned output base, eightLD plus a finalLHU
can inspect bytes0..65 without casting output+1 to uint64_t or reading beyond
the array; shifts/masks must map the two guards and all512 bits explicitly.
Use defined aliasing/memcpy access and validate actual scalar lowering later.

The old packed prefix counts corrupt bytes, whereas original C counts corrupt
bits. For a new complete-parent port retain exact original diagnostics through
an error-only per-bit fallback (or exact invalid-bit popcount), original flag/
vstart increments and combined guard increment. On error, preserve original
DETAIL fields and first20 limit; do not silently inherit altered error totals.
Precomputed masks/flags must derive from original fixtures and formulas, not
observed Spike payload. Fresh-input validation must accompany this optimization.

## 1MiB Layout Proposal

Blindly enlarging the existing144-byte record per call needs2,580,480 bytes
before input ROM/code and does NOT fit. Instead index oracle by(seed,op,VLslot):
32*10*7=2240 entries, sharing only identical semantics across mode/sticky.
Keep original nested runtime loops and all calls; sticky is ORed into baseflags.

| Conservative planned allocation | Bytes |
| --- | ---: |
|2240 exact two-mask oracle entries,128 bytes each|286720|
|Baseflags,one byte per entry|2240|
|At most48 full input ROM rows|49152|
|Original16 inputs plus1536 bit/flag fixtures if retained|12320|
|Original a/b/mask/output logical BSS|4354|
|Reserved stack|65536|
|Subtotal before alignment/code/runtime|420322|

Even allowing8192 runtime-log bytes and64KiB code leaves554526 bytes of1MiB.
This demonstrates a plausible layout, NOT an actual linked map/stack proof.
No17920-entry descriptor table is needed; source loops provide tuple identity.
Keep scalar alignment, array upper halves, helper history and failure fallback.

## Mandatory Work Floor And Honest Cost

Assume RV64 scalar-only packing with at most8 bytes/store and maximum grouping;
this is deliberately optimistic, not actual GCC output. Per-call minimum:

| Work retained | Per call | Whole17920 |
| --- | ---: | ---: |
|Fresh a/b SD-equivalent writes|256|4587520|
|Fresh128-byte mask writes|16|286720|
|Fresh130-byte output writes (16SD+SH)|17|304640|
|Read all64 result bytes and both guards, best aligned packing|9|161280|
|Original helper instructions, weighted vv/vf|19 average|340480|

These alone total5,680,643 instructions including capacity3. Input writes ALONE
exceed3M; no scalar gold packing preserving fresh data can meet a3M total gate.
The floor excludes input-ROM loads, expected-mask loads, comparisons, address/
loop control, call setup, tuple/flags/vstart checks, startup/ABI and diagnostics.
Keeping the existing full-row copy also needs4,587,520 input LDs; a straightforward
16-expected-LD/call two-mask checker adds286720, raising this incomplete subtotal
to10,554,883. Periodic input-word reuse could reduce those LDs, not the stores.
These are source/ISA bounds and proposals, not measured instruction profiles.

Existing accepted700 measured source reference:2,179,709 firmware instructions;
actual M9 simulator4549.983158s and2,176,351 retired instructions (about478.32/s).
See [HANDOFF](full700_m9_prepare01/HANDOFF.md) and
[terminal result](full700_terminal_recovery02/run01/result.json).
Plain25.6x scaling gives about55.80M firmware /32.36h. This is only a proxy:
700 has different op/seed/VL mix, and vector latency/concurrency change throughput.
Even the optimistic5.68M floor at that rate is3.30h; achieving3h would require
at least526/s BEFORE all omitted work. Neither calculation is a walltime lower
bound or proof of a current hardware stall; no full-parent measured rate exists.

## Decision

Whole17920 source-faithful bare portability and a1MiB layout are credible;
<=3M is statically impossible under retained scalar fresh writes, and <=3h is
not established. Keep full-parent acceptance OPEN. Do not simply raise700's
stop constant, clone its table, drop repeated inputs, partition history, or
launch hoping for early failure. Any later implementation requires an explicit
whole-scope cost/budget decision above this floor, then actual lowering and
full-source equivalence/reference/worker review. No such execution is proposed
or authorized by this note. Linux original-binary closure remains separate.
