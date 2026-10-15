# e64/m4 integrated scalar source proposal

Status: STATIC_SOURCE_ONLY_PENDING_INDEPENDENT_REVIEW. No Host test,
preprocessor, compiler, helper execution, Spike, VCS or RTL modification.
Only source text/list/layout analysis was run (audit_source.py, actual exit0,
tool receipt e47ac4). No permission to execute a compiled program follows.
All previous model/source artifacts remain unchanged.

## Delivered integration and remaining build boundary

case_proposal.c is the original recovery22 C with seven narrowly enumerated
edits: shape qualification/includes/alignment, CAP64 qualification, mask
setup replacement, per-call FP setup replacement, output initialization,
packed comparator guard, and successful-path element accounting.
source_integration.diff records every change. Failure function and complete
original fallback body are byte-identical to the recovered source. Original
RNG, nested loop order, helpers, function table, vstart check, first20 error
diagnostics, guard condition and final counters are retained.

The original Linux syscall/finish/_start wrapper is intentionally unchanged
in this SOURCE proposal. This is not a linked SoC executable or runnable
adapter. Later authorized software work must use the reviewed wrapper port,
not silently treat the original Linux ecall as a SoC completion protocol.
Original operations.h/rvv_matrix_e64_m4.S remain external archival inputs.

packed_output.h declares exact typed dictionary[1986][8] and IDs[5985][9].
Their definitions are NOT emitted here: later mechanical emission must
match the pinned m4 dictionary64.bin and indices_u16le.bin byte-for-byte
(LE u64/u16 respectively). No m2 dictionary, gold or capacity is imported.
FP source is the unchanged pinned sibling fp_period_proposal.h. Only the
mask implementation is adapted from reviewed e32/m2, with distinct e64m4
names and its own CAP64 proof. No e32 FP code or uint32 output logic is used.

## Full obligations, unchanged

All5985 calls/35ops/3seeds/383040 results/11970 guards/5985 vstart checks
remain one continuous original history. Physical groups v8..11, v16..19,
v24..27 and actual original13-instruction helper per call remain unchanged;
capacity3 +35*13 is458 static helper instructions. Target helpers remain
outside these scalar headers. No new RVV or hardware fence is introduced
at source level; eventual actual instructions still require examination.

Output initialization explicitly writes66 u64 words of0x000000000000005b,
including both guards. The comparator observes all66 actual u64 words
and66 expected words, even when an earlier word mismatches. It uses OR of
word XORs, not an XOR checksum that can cancel. It reads eight64B blocks
and only two words from the ninth block:528B, not576B. Last result offset512,
upper guard offset520. All9 IDs are used. No tail byte/guard is omitted.
Any mismatch executes the original entire scalar oracle and exact failure
policy; success increments elements by64 once. Both paths increment checks
once. Returned vstart is checked before either path.

Typed uint64 arrays stay naturally aligned; output/mask explicitly align8.
memcpy is used for mask clear, never a uint64 alias cast into uint8 backing.
The packed output's volatile uint64 reads use its actual uint64 objects,
not out+1 byte type punning. Dictionary pointers remain typed uint64. No
restrict promise is introduced. Stack and actual linker/map costs are not
yet proved; gold and full call metadata must not be placed on stack.

## Rewrite A: CAP64 mask, independent source proof

mask_setup.h tiles all128 bytes with16 ascending8B zero memcpy operations,
each followed by an empty compiler memory clobber. The case's mask object
is8B-aligned. The desired lowering is16 SD; source inspection does not
claim those actual instruction widths before compilation.

Only after the complete clear, each mode performs its ORIGINAL selected
indices in ascending order, with an explicit byte read/OR/write and memory
clobber after each update:
- mode0:0..63,64 cumulative byte updates;
- mode1:1,3,...63,32 cumulative byte updates;
- mode2:2,9,16,23,30,37,44,51,58,9 cumulative byte updates.

For each selected i, the destination byte is floor(i/8), value is its
previous value OR (1<<(i%8)). Repeated updates of the same byte are NOT
merged into a final byte or mask copy. mode groups occur outside trials:
3seeds*35ops*7VL*3modes=2205 groups,735 per mode. Required selected SB
events remain735*(64+32+9)=77175. Full clear covers282240 bytes via35280
intended SD, replacing only the original282240 zero SB. Upper120 bytes
remain zero; actual vlm consumes8 bytes at CAP64.

STATIC_PROOF.json compares actual new header indices against the source
predicate independently and the reviewed e32 source. It checks every
intermediate cumulative mask state from arbitrary nonzero backing through
full clear and selected updates, and compares final128B against m4 model
masks. This is a static byte-state proof, not running the C helper or Host.
The reused operation is SEW-independent because it addresses uint8 mask
bits at fixed CAP64, not element arrays; widths16/32/64 are not substituted.

## Rewrite B: FP64 periodic refresh, separate attribution

The FP call remains inside every original si trial, after mask setup and
before output initialization. All1890 FP calls, including VL0/no-op and
identical repeats, perform128 ordered u64 stores a0,b0,...a63,b63:
241920 stores/1935360B. The unchanged proposal freshly loads the original
8-word input table inside every FP call, dispatches seed0..2, and expands
eight periods of8 pairs. For i=8q+j, p[j]=input[(seed+j)%8], then
a[i]=p[j], b[i]=p[(3*j)%8], identical to original source. No seed-only or
cross-call destination refresh replaces those writes. Next seed restarts
the original RNG and integer input construction, not previous FP contents.

All640 original FP expected u64 words remain the oracle; no host FP model.
This source has no new fflags/frm checks or clears. Source model and macro
mapping proofs are pinned from full_e64_m4_source_model01, not rerun here.
The memory barriers are compiler ordering constraints, not emitted fences.
Actual load/store multiplicity, spills and ABI lowering remain future gates.

## Cost attribution: old actual code versus new uncompiled direction

The following OLD counts are derived from the pinned original m4 ELF's
disassembly and full original loop dimensions, not a measured new binary:

1. Original mask clear loop10420..1042a is4 instructions*128*2205=1128960,
   excluding its setup. Original selected-index loop10432..10458 plus
   nonfinal10552/10554 has six parent instructions per index, two extra
   per nonfinal index, seven RMW instructions per selected index, plus
   selected() at1012a:4/6/9 instructions for modes0/1/2 respectively.
   Thus each group's selected loop is64*(6+4/6/9)+126+7*(64/32/9),
   or1214/1118/1149. Across735 each:2558535 instructions. These TWO mask
   loop regions total3687495, excluding setup/outer bookkeeping.
2. Original FP refresh10488..104bc is22 instructions*64*1890=2661120,
   excluding its setup. This is separate from every mask saving above.

New mask source aims at16 SD plus selected LBU/ORI/SB triples, with fixed
small offsets, which would total266805 instructions across all groups
BEFORE dispatch/address/setup/spills. It is a constructive direction,
not actual GCC cost. New FP source's conceptual8LD+<=5dispatch+128SD+RET
leaf is<=142/call,268380 across1890, also NOT GCC/caller cost. Neither
number may be subtracted and reported as measured total firmware savings.
Mask clear/selection savings must never be called FP caching savings.

Packed init/check is a THIRD, separately accounted existing design:
66 output SD and66 actual LD +66 dictionary LD per call, with XOR/OR,
9 ID loads, dictionary addressing, eight-block loop control, final tail,
outer counters and original helper. Do not reuse the earlier illustrative
66-branch comparison cost: this implementation uses XOR/OR accumulation.
Future compiled accounting must cover all of these, the full fallback,
original RNG, table refresh/dispatch, mask setup, ABI and wrapper. No
whole-firmware upper bound or <=3h admission is established by this draft.

Exact prior model ROM components remain240402B (U1986), plus stated172200B
globals/runtime/code/stack reserves gives412602B, not an actual linker map.
The source expansion can grow code and spill; reserves are not evidence
that this final header fits or is fast. The next gate is independent SOURCE
review only, followed by separately authorized Host/compile/net-cost work.

## Review evidence and historical boundary

STATIC_PROOF.json contains exact source/code/data pins, seven-edit proof,
original fallback identity and complete per-mode mask events.
Own source model is already independently reviewed in
../e64_m4_source_review01/SOURCE_MODEL.md, SHA
c2af863f49827f27e59205df2914c7790da43e1c0235c0b78c79ed5f167c2a6d.
That does NOT accept this new integration or compiled behavior.

Archive resume03 recorded this exact original ELF board PASS. Current M9
full5985 regression remains incomplete/unaccepted. This proposal is not a
claim of a remaining RTL bug. Prior sealed inputs and unrelated work remain
untouched; no simulation, reference, helper execution or compilation ran.
