# Full17920 Scalar Lowering Proposal

Static successor to [feasibility01](full17920_static_feasibility01.md),2026-10-14.
No table/source generation, compile, Host, reference, DUT, trace reparse or live
query. Existing assets remain unchanged. Pseudocode is a design, not executable
or compiler-measured evidence. No budget increase or execution is authorized.

## Fixed Source Contract

Authority: prepared02/prepared/alias_v8_e16m8_prefix682/original/parent.c and
scenario.S, with existing original-ELF identity proof referenced in feasibility01.
Only this selected SEW16/M8/CAP512/unmasked/vstart0/boxed/vd=v8 parent applies.

| Original source | Obligation in this proposal |
| --- | --- |
|parent.c:42-45|32seeds*10ops*7VL*4modes*2sticky=17920, same nested order, no partition/reset|
|:49-50|All128 mask bytes freshly written before every helper, even vm1/VL0|
|:51-54|Both512-halfword inputs freshly written each call; upper512 of each declared1024 remain BSS zero|
|:55|All130 output bytes reset to5b every call, including bytes outside result/guards|
|:60 and scenario.S|Original helper bytes, arguments, capacity loads, boxed scalar, CSRs and all193 static instructions retained|
|:61|Nonzero low32 status adds exactly one returned-vstart error|
|:62-84|All512 result bits tested against exact allowed sets; each invalid bit adds one|
|:67|Old alias bits come from actual post-helper a[0..31], not a substituted golden|
|:85-86|One flags mismatch increment; one combined guard increment if either/both fail|
|:87-98|Same first20 DETAIL rule/fields/error totals,17920 final count and source exit condition|

There is no PRNG state to optimize away. Preserve lhs/rhs seed formulas and the
complete call history. All2560 VL0 calls still load operands/mask, manipulate
VL/fflags, store the result and run the oracle. Modes never suppress this vm1
target. No unrelated masked-inactive rule is imported.

## Periodic Inputs: Fewer ROM Reads, Same Fresh Writes

For each seed, lhs repeats every16 halfwords. vv rhs also repeats every16;
vf rhs is one constant halfword. Each period is exactly four little-endian u64
words. A source-derived ROM can provision16 lhs periods,16 vv rhs periods and
16 constant rhs periods: at most48*32=1536 bytes, without full1024-byte rows.
No table is generated here. Indices follow the original formulas, not a new RNG.

Pseudocode, where UNROLL denotes intended static scalar expansion:

```text
for seed, op, length_slot, mode, sticky IN ORIGINAL NESTED ORDER:
    prior = errors
    vl = [0,1,2,3,256,511,512][length_slot]
    # One 64-bit repeated-byte value; no mode-dependent skip.
    maskword = [0xffffffffffffffff,0xaaaaaaaaaaaaaaaa,
                0x2424242424242424,0][mode]
    UNROLL j=0..15: store64(mask+8*j, maskword)

    pa0,pa1,pa2,pa3 = load64_words(lhs_period(seed))
    pb0,pb1,pb2,pb3 = load64_words(rhs_period(seed,op))
    UNROLL r=0..31:
        UNROLL k=0..3:
            store64(a+32*r+8*k, pa[k])
            store64(b+32*r+8*k, pb[k])

    UNROLL j=0..15: store64(output+8*j,0x5b5b5b5b5b5b5b5b)
    store16(output+128,0x5b5b)
    status = ORIGINAL_functions[op](a,b,output+1,vl,512,mask,0,sticky)
    ORIGINAL_FULL_ORACLE_AS_BELOW
```

All addresses above are byte offsets. The two-store interleave follows the
accepted packed-input grouping, not literal original halfword store granularity.
No write crosses offset1023 in either input,127 in mask or129 in output.
32*8SD=256 input writes per call;18,350,080 original halfword assignments are
represented by4,587,520 SDs, not removed. Constant vf data still needs all128SD
to b; its original full b-vector load and scalar b[0] load remain.

Load the periods afresh each call; do not assume caller-saved registers survive
an original helper. Eight pattern registers plus two bases fit RV64's register
set, but actual allocator/spills need later inspection. Fixed offsets0..1016 fit
signed12-bit SD immediates, permitting one pair of bases and no per-store address
increment. Full expansion is roughly1024 bytes for256 uncompressedSD instructions,
not17920 copies of the body. A loop alternative is not silently substituted into
the cost model. Scalar SD/SH can use reviewed inline-assembly memory accesses,
or defined memcpy/GNU-may_alias lowering with explicit freshness enforcement;
no unaligned uint64_t cast, strict-aliasing UB, added RVV, CSR or FP instruction.

## Two Logical Oracle Masks And Actual Old Data

Provision W[seed][op][8] = fixture wanted bits and M[length_slot][8] = i<VL.
These are two logical masks, NOT a canonical Spike output or the old packed
prefix's precomputed must-one/must-zero table. W depends on original fixture
indices and op<4?op:op-4. It does not depend on mode/sticky/VL. BaseFlags for
each(seed,op,length_slot) ORs only the original active fixture flags.

For each64-bit result chunk, old is the corresponding8 bytes of actual a after
the helper. These8 chunks cover a[0..31], exactly parent.c:67 for i0..511.
This retains the original dynamic memory expression even if that memory differs
from its expected initialization. An independent checker must also enforce fresh
input writes and reject unintended memory stores; it must not replace old reads.

For VL>0:

```text
bad_active = (actual XOR W) AND M
bad_tail   = (NOT actual) AND old AND W AND (NOT M)
bad        = bad_active OR bad_tail
```

Proof for a tail bit: original allows {old,1,wanted}. Actual1 is always allowed;
actual0 is forbidden only when both old and wanted are1. VL0 is different:
every bit must preserve old, so bad=actual XOR old, regardless of W or M.
All bitwise operations are unsigned64, masked by their natural width. No shift
by64, signed complement, checksum cancellation, or boolean-per-word error count.

Aligned output reads preserve the original output+1 placement without OOB:

```text
previous = load64(output+0)             # includes leading guard
leading_guard = previous AND 255
UNROLL j=0..7:
    next = load64(output+8*(j+1)) if j<7 else load16_unsigned(output+64)
    actual = (previous >> 8) OR ((next AND 255) << 56)
    old = load64(a+8*j)
    wanted = load64(W+8*j)
    active = load64(M+8*j)
    bad = (actual XOR old) if vl==0 else
          (((actual XOR wanted) AND active) OR
           ((NOT actual) AND old AND wanted AND (NOT active)))
    # Error-only exact popcount, no optional Zbb instruction assumed.
    while bad != 0:
        errors += 1
        bad = bad AND (bad-1)
    previous = next
trailing_guard = previous >> 8          # byte65, unsigned16 load above
```

All8 chunks continue even after a mismatch; no early return or loop short-circuit.
All64 result bytes and both guards are actually read. Bytes66..129 are initialized
but remain outside the original post-helper oracle. Carrying adjacent loads in
registers avoids duplicate loads; it is not cached acceptance across calls.

Then perform the source checks in source order (vstart before bits; flags and
guards after): low32(status)!=0 adds1; high32(status)!=(BaseFlags|sticky) adds1;
(leading!=0x5b OR trailing!=0x5b) adds1 total. Both bad guards must not add2.
Pseudocode places the bit kernel separately only for readability. Keep prior,
short-circuit details++<20 and source error output unchanged. Maximum per-call
errors are512+3, so whole-parent accumulation stays below unsigned32 overflow.
Two invalid bits in one byte add2; identical errors in different words do not
cancel; later good words never clear earlier errors.

## Planned Layout, Not A Linked Map

W needs32*10*64=20480 bytes; M needs7*64=448; BaseFlags needs2240 bytes.
The fixture flags are0/16, so one byte suffices without dropping any original
flag bit. Period ROM<=1536 bytes. Keep original fixtures12320 bytes if desired,
logical a/b/mask/output BSS4354, runtime reserve8192, stack64KiB and text64KiB:
total180642 bytes before remaining alignment/metadata, comfortably below1MiB.
This is allocation arithmetic, not generated unique-row counts or stack proof.
Actual linker map, fixed stack reserve and scalar-only disassembly remain gates.

## Lowering And Budget Envelope

This is a hand-planned all-correct path, not actual GCC output or an executable
upper-bound proof. A later build must account for every prologue/spill/rematerialized
address/backedge/call and all failure entry PCs. Reject cost admission if its
actual CFG exceeds a separately authorized limit; do not edit flags to chase it.

| Planned retired work per call | Allowance / derivation |
| --- | --- |
|Mask selection/base/value setup +16SD|28|
|Period/index/base setup +8LD +256SD|304 (40 setup allowance)|
|Output value/base setup +16SD+SH|25|
|Original helper|19 weighted average, exact340480 whole|
|Packed bit kernel|168:33LD/LHU,24 reconstruction shifts/OR,64 logic,8 zero-error branches,39 other/control allowance|
|Status/flags/combined guards|32|
|Tuple addresses/call/ABI allowance|128|
|Loop/case/error-detail gating|24|
|Subtotal|728 per call|
|Further spill/rematerialization reserve|272 per call|

Thus a planning envelope is1000*17920+250000 fixed startup/summary allowance
=18,170,000 instructions. It is NOT a certified ceiling: code not implementing
the specified schedule, compiler duplication or extra runtime work can exceed it.
The fixed allowance is a reservation, not measured startup. Error paths execute
additional exact-popcount/diagnostic work; up to4 simple scalar instructions per
bad bit would add36,700,160 instructions at512 errors/call, plus diagnostic and
status/control overhead. UART/device stalls have no static walltime guarantee.
Do not use the all-correct envelope to promise completion after arbitrary errors.

An implementation-specific floor already includes5,178,880 fresh stores,
161280 output/guard reads,143360 actual-old reads,286720 W/M reads,143360 period
reads and340480 helper instructions, plus capacity3 =6,254,083 instructions,
BEFORE checks/address/loop work. Earlier5.68M is a weaker floor, not contradicted.
No scheme here makes3M possible. At accepted700's478.32 retirements/s proxy,
the18.17M planning envelope is about10.55h; even this method's incomplete floor
is about3.63h. Different op/VL mix or host concurrency changes that rate, so
neither is a measured full-parent walltime nor an absolute hardware lower bound.
No <=3h admission is supported and no larger budget is requested by this note.

## Later Verification Obligations, Only After Separate Authorization

One complete source-derived model must bind all17920 tuples,9,175,040 bits,
35,840 guards,17920flags/vstarts and340480 helper instructions; no subset sampling
can establish full equivalence. Original fixtures/formulas independently define
W/M/BaseFlags and periods. Original C vs proposed oracle must agree on exact
error totals, not just PASS, including all8 combinations of(actual,old,wanted),
VL0, active/tail boundaries and mixed permitted tail values.

Targeted negatives should include changed post-helper old memory, two invalid
bits in one byte, two-word identical errors, final bit511, both guards at once,
upper input/mask/output-init omissions, deleted/reordered fresh call intervals,
VL0/sticky/mode/history deletion and failure-detail count20/21. Intended scalar
loads/stores, no added RVV, all original helper bytes/CSR sequence and actual
numeric exit must be proved from the eventual linked ELF and closed execution.
No such artifact or result is claimed here. Full17920 remains an open objective;
accepted700 and historical Linux-program/root-cause boundaries remain unchanged.
