# e8/m8 Sentinel And Mask-Unroll Proposal

Status: SOURCE-LEVEL STATIC PROPOSAL ONLY. No candidate C/header has been created.
No compile, Host, reference, VCS, RTL edit, raw scan, active process/trace query
or budget change is authorized or performed by this work. Existing e8 assets
and running e16 assets are untouched. Submit to Averroes before any next stage.

## Actual Baseline

Baseline: ../full_e8_m8_block_unrolled01. Original Linux identity in proof.json:
ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f.
Actual SoC ELF SHA847bdfe2e4d261225c06df8de0de2535af60500f272e725d91f42f1900da0c67.
Actual Spike ELF SHA8b32f84fd05e8ff61acd6417770fe5d4154aa93d5fe180171af4ca9022d35fba.
Old READY is reference-only PASS, actual reference/audit0, firmware2825046;
that is not current-DUT acceptance or a guaranteed runtime prediction.

ARTIFACT_AUDIT02.json is authoritative static facts. Its parent audit verified
all disassembled instructions against each ELF, complete source dictionary
bytes against linked symbols, all4095x17 linked uint16 IDs against sequence.json,
all384 mask-table bytes, exact chronological seed/op/VL/mode/start contexts,
original3+325 helper code windows and capacity's encoded vtype3.
It does not execute the original model or regenerated software fixtures.

Required invariant scope: SEW8/CAP1024/LMULm8/vtype3, physical8 registers per
group and1024 input bytes each, original4095 calls/25 ops/three seeds in order,
4193280 result bytes,8190 byte guards,4095 returned vstarts,53235 helper
instructions. Helper output pointer remains out+1, not the e16 out+2.
Preserve every original seed/RNG write and state transition, helper bytecode,
masked/prestart/tail behavior, fallback byte loop and exact error counts.
Do not shrink history, hash/checksum results, change flags or add RVV/fences.

## e8-Specific Geometry

The first dictionary ID is independently verified in both actual linked ELFs:
all8 words are0x5b5b5b5b5b5b5b5b. This is byte91 repeated64 times, NOT e16's
0x005b005b005b005b. First16 IDs cover1024 checked bytes; final ID covers2 bytes.
Output initializer is128 raw8B writes plus one2B write at offset1024.
Keep all1026 fresh bytes per call,128 actual LD plus final LHU,528255 total
output reads. Do not use a4B tail, read beyond1026, or compare tail as full64B.
The final2B comprises the last result byte and right guard; it is not dispensable.

There are65520 full-block positions: ID0=52335, nonzero=13185.
Per-seed ID0 counts are17445/17445/17445. Per-block/per-op distributions are in
the machine-readable facts. Equality with an e16 count is an independently
observed coincidence, not an assumed/copied profile. Final-partial ID0 count0:
the padded2B dictionary value cannot equal the full64B sentinel.

e8 uses all128 predicate bytes/all1024 bits. Unlike e16/m8, there is NO
upper64-byte-zero contract. Preserve three actual masks and1575 original
per-group epochs, sixteen8B stores each,25200 stores total. Do not move writes
between groups or replace a/b/mask initialization with final snapshots.

## Single Proposed Delta

Only a new successor packed.h would change; case.c, original fallback,
dictionary, IDs, sequence, inputs, source model, helper assembly and flags stay
byte-identical. No current implementation or lowering claim is made.

1. One lexical uint64 constant0x5b5b5b5b5b5b5b5b in packed_mismatch. At each of
   the sixteen existing full-block sites, load the original ID. If ID==0,
   perform all8 raw_word reads and compare to that constant, returning1 on the
   first mismatch. Otherwise retain the original8 expected-word comparisons.
   Keep original BNE-style early fallback; do not introduce per-word
   SUB/SNEZ/OR/sticky accumulation. Lexical constant placement does not promise
   one actual materialization per call.
2. Replace initialize_mask's fixed16-iteration8B memcpy loop with sixteen
   explicit8B memcpy statements at offsets0..120 in the same logical epoch.
   Preserve full128B data, including every high predicate bit, and actual
   compiler-scheduled same-epoch stores. No loop/control opcode is required
   semantically; no new vectorization, asm hints or flag experiments.

Keep original final uint16 tail memcpy and uint16 expected-dictionary cast
verbatim. Old linked tail already uses two LHU and a single SUB/SNEZ return;
that existing final scalar comparison is not a per-word sticky strategy.
Keep all129 output reads, both byte guards and original byte fallback, even
where the whole output happens to equal the sentinel.

## Actual Old CFG And Conditional Savings

Old equal-output packed_mismatch is451 instructions in BOTH actual linked
backends (SoC entry80000076, Spike80000082),1846845 instructions across4095.
The static walk follows the original acyclic successful compare branches,
not an instruction-set execution or runtime measurement.
Fullword checks use1 BEQ+127 BNE; final tail uses SUB/SNEZ once per call.
The128 old fullword gold LDs/call total524160; tail gold is LHU4095, NOT LD.
Specializing ID0 can remove418680 fullword gold LDs, leaving105480 fullword
gold LDs plus4095 tail LHU=109575 gold scalar reads. All69615 ID LHU remain.
Actual result reads and original writes/helpers are never counted as savings.

The linked old full-block address sequence has a shift6 and base ADD per ID;
up to104670 such address operations also become unnecessary on zero paths,
but a future compiler might speculate or rearrange them. Thus523350 is a
gross instruction opportunity, not proven net saving. A one-branch-per-site
implementation would add65520 ID-selection branches. With materialization
cost M, joins J and all remaining signed layout/spill/setup delta L, the simple
same-layout comparison ledger would be:

    comparison saving =457830 - M - J - L

This is a transparent sensitivity ledger, not an actual new linked CFG.
For illustration ONLY, with J=52335 and L=0:
constant4/zero-block gives196155, constant8/zero-block gives-13185; a shared
constant costing3/call would give393210. e8's long byte5b pattern must NOT
inherit the e16 four-instruction construction or its measured saving.
The old initializer currently uses an ELF literal load for this constant;
new comparator hoisting versus rematerialization remains unproved.

Old Spike mask loop80000b36..80000b42 (SoC relocated counterpart) executes
four common instructions16 times and two additional instructions15 times:
94 instructions/group,148050 over1575 groups, per actual static_cost02.json
and disassembly. It includes15 LD+16 SD; first word is provided outside the
loop, sometimes by known mode0 constant. An ideal explicit16LD+16SD core
would be32/group, giving97650 loop-core opportunities conservatively before
surrounding changes. This is NOT a linked whole-main saving: first-word
handling, setup/addressing, register allocation/spills, joins and scheduler
changes must all be included in future actual-CFG accounting.

No new net saving or candidate firmware total is established at source level.
Potential memory-load reductions are concrete; the net can shrink or reverse
after lowering. One legal source candidate is proposed, not a parameter sweep.

## Later Gates, Not Current Authorization

If separately authorized, create a new software successor with exactly those
two deltas; preserve case.c/fallback bytes. Check original/new byte equivalence
and all offsets/guards including1024/1025, mutation at every checked byte,
all three complete predicates including high64B, untouched state/history and
UB/alignment without typed-pointer casts. Keep no-extra-RVV/helper byte checks.
One actual dual-backend compile and full linked CFG would then count every
branch, constant build/load, join, spill, call/return and mask setup against this
e8 baseline. Do not silently borrow e16 addresses, layouts or savings.
Only an independently accepted actual source/artifact/cost gate could justify
seeking reference authorization. This proposal authorizes none of those steps.

Runtime remains uncertain: fewer firmware instructions do not establish
<10800s completion, and no old timeout is evidence of deadlock by itself.
No active task is sampled here, no watchdog/runtime settings are changed,
and no6h/extended budget or new DUT/ref launch is inferred.
