# Unboxed Unmasked E16/MF4: Full17920 Static Assessment

2026-10-14. Static source/helper/metadata review and small identity hashes only.
No model/table generation, compile, Host, reference, DUT, live query or large
trace read. This selects the actual original parent, not alias-m8 or a simpler
fixture. No implementation or execution is authorized by this document.

## Identity Is Available

Original ELF:
/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions46/binaries/rvv_fp_compare_unboxed_unmasked_e16_mf4.
It and fp_compare_unboxed_prefix265_prepare01/software/original_rebuilt.elf
were freshly hashed: both
404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152.
No rebuild was performed. Full source files are under that preparation's
software/original/ (parent.c is full source, not the265-call port):

| File | Fresh SHA256 |
| --- | --- |
|parent.c|03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad|
|scenario.S|33abaa5c662a3780ac82ea631fec6909a035ccbb6b9d656896ce0cb356808bbe|
|fixtures.h|5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1|

[source_elf_proof.json](fp_compare_unboxed_prefix265_prepare01/source_elf_proof.json)
binds SEW16, UNMASKED1, UNBOXED1, RESTART0, DESTINATION_KIND0.
[Independent source review](fp_compare_unboxed_prefix265_reference_audit01/REVIEW.md)
already verified the complete original rebuilt ELF and all helper machine bytes.
There is no currently identified exact-source/rebuild blocker for this parent.

## Own Geometry And Original Malformed Boxing

- VLEN1024, CAP16, e16/mf4, vtype14. Each source occupies32 bytes of a physical
 128-byte register: v8 and v16, not eight-register groups. vd=v24 is disjoint.
- 32seeds*10ops*7lengths*4modes*2sticky=17920 calls in original nested order;
 lengths0,1,2,3,8,15,16. There are2560 VL0 calls,7168 vv and10752 vf calls.
 Preserve all17919 predecessors of the final call, with no per-partition reset.
- Helpers: capacity3 instructions, four17-instruction vv and six19-instruction
 vf;185 static instructions,326144 dynamic helper instructions plus capacity3.
 Every helper loads both full16-halfword sources, vlm-loads old destination
 v24 from output+1 AND mask v0, selects requestedVL, writes sticky fflags,
 compares, reads vstart/fflags, restores caller flags, restores capacity and
 vsm-stores two result bytes. No helper instruction is removable, including VL0.
- vf uses original `lhu t2,0(a1); fmv.d.x ft0,t2`, without the boxing OR used by
 the separate alias-m8 program. Actual raw scalar bits are zero-extended b[0],
 changing with seed. The upper48 zero bits make this an invalid FP16 NaN box;
 the original C explicitly selects fixture rhs index14 (qNaN) for op>=4.
 Do not replace fmv.d.x with a half-load, box the value, or set all ft0 to0.
- Raw lhs and b inputs still follow original seed formulas, no mutable PRNG:
 lhs_index=(i+seed+7*(seed/16))%16; vv rhs=(3*i+5*seed+seed/16)%16;
 vf rhs=seed%16. Only expected comparison semantics substitute qNaN rhs.

All seeds matter: for EQ/NE-vf, invalid boxing supplies qNaN, but an active lhs
sNaN still raises NV. Ordered vf LT/LE/GT/GE raises NV for any nonempty active
range because rhs is qNaN. VL0 contributes no new flags. Sticky is still ORed
in; expected.flags must be taken from the full original table rather than
hardcoding zero or NV for every vf call. The prior seed0/op4/VL15 boundary
excludes lhs15 sNaN; VL16 and other seed rotations must not inherit its NV0.

## Exact Oracle And Freshness

Full checks:286720 result bits,35840 guard values,17920 flags and17920 returned
vstarts. All128 mask bytes and all130 output bytes are initialized per call.
Both a/b declared1024-halfword arrays retain original BSS; only first16
halfwords (32 bytes each) are freshly written per call. Their untouched upper
1008 halfwords must not be repurposed as storage or polluted by widened writes.
Logical vlm mask/result footprint is two bytes, not128 bytes, but original
physical128-byte scalar mask initialization is still mandatory.

**Old-value semantics are NOT alias-m8's dynamic a[] reads.** DESTINATION_KIND0
keeps `old=(0x5b>>(i%8))&1`, so the16-bit old result is exactly0x5b5b. The helper
loads those initialized destination bits from output+1. The original oracle
does not read post-helper a/b for old; adding that substitution would be wrong.
Actual pre-helper writes/old-vd load and post-helper result reads remain checked.

For each bit: VL0 requires old; i<VL requires fixture wanted; a nonempty range's
tail allows {old,1,wanted}. Mode does not predicate this vm1 target, but mask
loads/writes and every mode call remain. No masked-inactive rule is imported.
Precompute two16-bit masks Z/O meaning must-zero/must-one, plus BaseFlags,
indexed by(seed,op,length_slot), directly from original fixtures/formulas.
Then `bad=(actual & Z) | ((~actual) & O)` restricted to16 bits. This preserves
all legal independent tail choices, not one reference result.

The full output buffer remains130 bytes, not four. Only result bytes1..2 and
guards0/3 are postchecked by the original. On an aligned output base one LWU
reads precisely these four bytes without a misaligned uint16 pointer or OOB:
actual=(word>>8)&0xffff; leading=word&255; trailing=word>>24. Initialize all130
bytes before every helper with16SD+oneSH at128; do not tighten bytes4..129 into
new post-result constraints or omit their initialization.

Error count must equal the original: each set bit in bad adds1, not one per
byte/word; low32(status)!=0 adds1; high32(status)!=(BaseFlags|sticky) adds1;
either/both bad guards adds one combined error. Preserve prior, first20 DETAIL
records and exact diagnostic fields/final count/exit. Maximum errors19/call,
340480 total, fits original unsigned counter. A scalar clear-lowest-bit loop on
the failure path avoids optional Zbb and retains two-errors-in-one-byte behavior.

## Source-Faithful Packing Candidate

Each source's16 halfwords is already one four-u64 period: **no repetition loop**
is needed for CAP16. At most48 such periods (16 lhs,16 vv rhs,16 constants) use
1536 ROM bytes. Every call loads its actual four A and four B words and writes
all eight fresh SDs, even if equal to the previous call. Do not reuse readonly
source pointers as a/b, skip writes for vf, or cache acceptance across helpers.

```text
for seed/op/length/mode/sticky IN ORIGINAL ORDER:
    g = oracle[seed][op][length]        # Z16/O16/baseflags + source-row metadata
    write_all_mask128(mode)            # 16 scalar SD, no skip for mode0/VL0
    for k=0..3, statically expanded:
        store64(a+8*k, load64(A_period+8*k))
        store64(b+8*k, load64(B_period+8*k))
    write_all_output130(0x5b)          # 16SD + SH, exact end129
    status = ORIGINAL_functions[op](a,b,output+1,vl,16,mask,0,sticky)
    if low32(status)!=0: errors++
    word = load32_unsigned(output)     # no early skip, even on bad status
    bad = ((word>>8)&0xffff & Z) | ((~((word>>8)&0xffff)) & O)
    errors += exact_scalar_popcount(bad & 0xffff)
    if high32(status)!=(baseflags | sticky): errors++
    if (word&255)!=0x5b OR (word>>24)!=0x5b: errors++
    ORIGINAL_detail_limit_and_case_increment()
```

Memory accesses must have defined aliasing/alignment, with a scalar-only
volatile/asm contract that prevents freshness elision; never cast output+1
to a wide pointer. Complete source/helper order and CSR writes are unchanged.
Period values may reside in registers only within the call's initialization;
do not assume helper-clobbered integer or FP registers survive. Original actual
raw b[0] must still feed every fmv.d.x, including later nonzero seeds.

## 1MiB Layout And Conditional Cost Target

2240 oracle entries of8 bytes suffice: Z16/O16/baseflags8/VL8/Arow8/Brow8.
Row IDs fit48; no full17920 payload table is necessary. Mode/sticky remain
original loops and BaseFlags is ORed at runtime. Planned oracle17920 + periods
1536 + logicalBSS4354 + originalfixtures12320 + runtime8192 + stack65536 +
text65536 =175394 bytes before alignment/other metadata. This is plausible
1MiB capacity, not a generated dedup result or linked stack/map proof.

Unavoidable planned scalar memory work is41 stores/call:8 inputs+16 mask+
17 output. With eight input LDs,one output LWU andone oracle LD, and the exact
original helpers, an incomplete lower bound is1,240,067 instructions. This
omits addressing, masks/status comparisons, loop/ABI, additional metadata loads
and runtime. Unlike alias-m8, this lower bound does NOT rule out3M.

An explicit **uncompiled design allocation**, to be falsified by actual CFG:

| All-correct path per call | Instruction allowance |
| --- | ---: |
|Fresh stores41 and input LD8|49|
|Original helper, use worst19 rather than17/19 average|19|
|Eight arguments/function selection/call|11|
|Actual output/oracle loads, packed extraction/bad predicate, flags/vstart/combined guards|29|
|Input/oracle addressing, mask and sentinel materialization|22|
|Original nested enumeration, case/detail gating|8|
|ABI/spill/reload allowance|13|
|Additional lowering reserve|9|
|Total target per call|160|

With a separately accounted100000 fixed startup/summary allowance this is
2,967,200 instructions, only32800 below3M. This is **not a proven upper bound**:
some op/helper choices cost less, but extra spills, repeated address generation,
branch layout, metadata checks or runtime can consume the entire margin. Keeping
g across the helper requires actual ABI allocation proof; a reload must be
charged. All17920 calls, including all errors in a full failing run, remain in
scope. Error popcount/DETAIL paths cost more than this zero-error allocation;
they cannot be hidden or treated as successful full completion on truncation.
No compiler/ref admission or deadline enlargement follows from this estimate.

## Existing Measurement And Decision

[M6 recovery](fp_compare_unboxed_prefix265_terminal_audit01/recovery01/REVIEW.md)
accepts only265 original calls, including op4/VL15/NV0, with730916 firmware
retirements to actual CTRL exit. The original reference count701895 differs;
do not interchange runtime/stop definitions. Direct scaling of730916 by17920/265
is49.43M for the OLD byte-init/per-bit implementation, not new packed cost.
VCS CPU1225.070s survives, but no durable child walltime/numeric exit survives
the old metadata failure; it is not a trustworthy full-program walltime proxy.
The separate alias700 rate is a different shape/mix and no <=3h guarantee here.

Conclusion: exact source/ELF provenance and memory capacity are sufficient for
a concrete static candidate. Original malformed boxing is preserved, not fixed
in the test. A3M all-correct implementation is plausible but currently unproved
and margin-sensitive; do not claim the cost gate passed. If eventual complete
CFG exceeds the unchanged gate, HOLD this parent rather than shrinking scope,
dropping fresh stores, choosing another fixture or silently raising a limit.

Later proof obligations, not tests executed now: all17920 ordered tuples and
all32-seed raw inputs/flags; original table vs independent FP16 classifier;
VL0 exact-old and tail allowed alternatives; first/last result and both guards;
two-bit exact error counting; all130/128/64 setup bytes; actual nonzero unboxed
ft0, no added boxing instruction; full185 helper/capacity encodings, actual
mf4/vtype14/CTRL runtime mapping, ABI/freshness and phase-qualified failure PCs.
The old265 acceptance and original ERROR remain untouched. Complete17920 and
original Linux execution remain open, with no new simulation or RTL finding.
