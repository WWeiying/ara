# Original e32/m4 Full5985 Static Plan

Status: STATIC_SOURCE_AND_ROM_FEASIBLE_COST_NOT_ADMITTED.
Only source, existing disassembly, ELF bytes and closed metadata were read.
No full model/gold generation, Host test, compilation, reference, DUT, RTL edit,
live-process query or active trace read. Running e32/m2 is untouched.

## Identity And Exact Source Scope

Archive: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04`.
The original `overlay/opt/ara-tests/rvv_matrix_e32_m4` and recovery22 rebuilt ELF
both SHA4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9.
The recovery report records exact ELF and disassembly equality. Recovered C is
binary-equivalent reconstruction, NOT proven original C text or Linux replay.
SOURCE_PINS.json binds the original m4 .S, e32 header, C and original ELF.
No existing e32/m4 full source-port artifact was found in this arithmetic
directory's bounded filename inventory; this is not a live-job search.

Source anchors in recovery22/reconstructed_oracle.c:
10-18 uint32 type/backings;94-119 capacity, RNG and nested trial order;
122-126 EACH FP call's input refresh;128 exact fill;138-168 original helper,
returned-vstart, full results/guards and mismatch fallback. Original header
operations.h:36-41 gives35 operations, kinds, eight FP inputs and640 expected
uint32 patterns. No host floating arithmetic may replace that table.

Original .S:5 selects e32,m4,tu,mu. At required VLEN1024:
CAP=1024/32*4=128; vtype18; groups v8..11,v16..19,v24..27 each512B.
The future port must dynamically verify this capacity and join all FOUR128B
physical registers, not reuse m2's two-register observations.

Read-only decoding found458 original helper instructions,1688 bytes:
capacity at10906..1090c, then35 exact13-instruction windows through10f9c.
Capacity encoding0122f557; full-VL012772d7; target-VL0126f2d7.
The helper-byte SHA is d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e.
Original target encodings, including op24 memory target, remain unchanged.
Do not patch m2 vsets, reuse m2 helper bytes, or add RVV to scalar setup.

The35 kinds contain30 three-start operations and five one-start operations
(19,20,21,22,23). Thus3 seeds*7 VL*3 masks*(30*3+5)=5985 calls, not4095.
Preserve seed/op/li/mode/si nesting, duplicate tuples and all5984 predecessors.
VL list:0,1,2,3,64,127,128. Starts:0,VL/2,(VL<CAP?VL:CAP-1);
the five nonzero kinds use start0 only. Original RNG runs128 xorshift steps
per seed, followed by original per-index overrides. Do not repeat a CAP64
input buffer. Integer source assignments:3*(256+16*7)=1104.

| Exact obligation | Derived count |
| --- | ---: |
| Calls / FP calls |5985 /1890 |
| Full uint32 results / uint32 guards |766080 /11970 |
| Returned-vstart checks / helper instructions |5985 /77805 |
| Exact output bytes / complete8B words per call |520 /65 |
| Packed positive output reads / initializer SD |389025 /389025 |
| Fresh ordered FP destination SW per call / total |256 /483840 |
| Proposed fresh immutable input LW per FP call / total |8 /15120 |
| Mask groups / proposed clear SD |2205 /35280 |
| Selected SB, mode0/1/2 per group |128 /64 /18 |
| Total selected cumulative SB |735*(128+64+18)=154350 |

Output byte0..3 is guard0x0000005b;4..515 contains128 results;516..519 is
rear guard0x0000005b. Word0 is frontguard+element0. Word64 at512 contains
element127+rear guard, NOT all guard, a short tail or representation padding.
Typed initializer is0x0000005b0000005b, not repeated byte0x5b.
Retain original a[1024],b[1024],out[1026],mask[128] backing. Only520 output
bytes are initialized/read. Software mask clears all128B each group; actual
vlm atCAP128 reads16B. Selected indices2,9,...121 give18 mode2 assignments;
bytes16..127 remain zero, not omitted from fresh setup coverage.

The original oracle is data/guards/vstart only, NOT fflags/frm correctness.
Do not extend a future reference's CSR visibility into a DUT flags claim.

## Golden Table And Model Boundaries

Original fp_expected640 words match ELF file0x15b0..0x1faf exactly, uniquely;
SHA b6ba4a7cb146e697a04723349b9e023e2210dc0714b717f70eb8bfb6c3a8438a.
Eight input words match file0x1590..0x15af; they occur five times as bytes in
the ELF, so byte-search uniqueness is not an identity proof. Original code
103ce..103dc stores base112d0 into stack120;1048c/10496 and104a6/104ae load
from that base+0x2c0+4*index =11590+4*index. Readelf LOAD maps VA=file+10000.
This code-bound identity replaces an initial static reader's rejected
assumption that the eight-word byte pattern had to be unique. No execution
or artifact change was needed. Expected-table access at1082e binds115b0.
Full640-word identity is not exhaustive FP-pair coverage: the original indexing
visits eight pairs per seed,24 distinct table indices per FP operation across
three seeds. Keep that exact source selection rather than expanding its claim.

Reusable mathematics: original e32 signed/unsigned operations, bitwise FP
table indexing, RNG algorithm, selected(), source fallback and history rules.
Must independently derive for m4:128 RNG outputs per seed, all new VL/start/
slide/gather boundaries, reduction/compress gold, full512B register groups,
520B packing, masks and m4 helpers. No m2 CAP/gold/ELF substitution.
b[2]=0xffffffff remains out of range; b[3]=32 is valid forCAP128. Every random
gather index must be re-evaluated against128, not64. Slidedown at126/127 also
uses128, and reduction/compress consume the actual new VL/mask histories.

Future owner logic must derive from this actual sequence. Only exact op19
38813c57, unsigned offset2>=VL can additionally omit a target owner. Baseline
start>=VL no-ops and extra nonempty VL1/2 cases must remain separately counted;
all actual alloc/done tokens and all five memory-helper owners still pair.
No masks, target results, helper windows or returned-vstart checks are waived.

## One FP Refresh Proposal

Use the already compiled e64 FP-period strategy, with e32-specific uint32
types and FOUR-byte destination operations. Its actual proof establishes a
strategy, not m4 code generation, cycle cost or permission to use eight-byte SD.

Inside EVERY original op>=25 call, before output fill, read all eight original
immutable uint32 fp_inputs through a const-volatile-qualified pointer into
eight local bit values. Then select seed0/1/2 and emit a fully unrolled ordered
a[0],b[0],a[1],b[1],...,a[127],b[127] list. No persistent seed-stack cache and
no per-destination table/cache LW is intended. There is no refresh outside
the FP call and no VL/vstart/equal-value shortcut. The next seed restores the
complete original integer RNG setup before any new integer call.

For i=8q+j, q0..15,j0..7:
(i+s)%8=(j+s)%8 and(3*i+s)%8=(3*j+s)%8. If local p_j=table[j], the seed-s
store pair is a[8q+j]=p_((j+s)%8), b[8q+j]=p_((3j+s)%8).
Resolve these variable names and offsets statically in three seed paths,
not by a runtime local-array index that silently recreates per-SW cache LW.
Sixteen explicit8-element periods cover each destination exactly once.

Proposed store idiom (not compiled here):

```c
static inline __attribute__((always_inline))
void put_u32(uint32_t *dst, uint32_t value) {
    __builtin_memcpy(dst, &value, sizeof value);
    __asm__ __volatile__("" : : : "memory");
}
```

The empty compiler barrier is not a hardware fence. It preserves each write
and order across otherwise equal-value stores; actual compiler output must
still prove256 SW per path, no SD merge, no omission or source RVV. Actual
artifact inspection, not this C idiom, will establish lowering. Table loads
must be fresh every FP call (including VL0), eight exact4B reads of original
const input bits; reading redundant immutable values fewer times does not
change original numerical input semantics. Do not compute floats or change
the original640 expected patterns or mismatch fallback.

## UB, Registers And Footprint

Keep uint32 values as bit patterns. Added indexing has maximum3*127+2=383,
but proposed resolved indices are0..7; all destination offsets0..508 fit
the original arrays and signed12-bit addressing. memcpy avoids uint64 pointer
type-punning/alias and alignment UB. Array/table storage is distinct and no
source table write is added. Output packing must also use memcpy, with future
actual ELF addresses/BE checked, and may not access rounded-up576B output.

Original unsigned RNG/shift arithmetic wraps as specified; shifts remain
masked to0..31, not64. Integer multiplication uses uint64 and division guards
remain unchanged. Original signed_word conversion and signed right shift have
implementation-defined aspects, not new UB; retain the same RISC-V GCC contract.
No new signed float conversion, floating arithmetic, restrict/pure promise or
algorithm change is proposed. Preserve original fallback exactly.

Eight local values plus two destination bases, table/seed/dispatch temporaries
fit a plausible small leaf register allocation, but GCC may spill or clone the
function and its caller. Use a noninlined refresh body with explicit inline
put_u32 operations to limit values live across the large main loop. This is
not a no-spill guarantee. Signed LW extension must not alter low32-bit SW data;
any compiler masking, loads/spills/caller saves count in the actual cost.

Three unrolled256-SW paths use about3072 bytes of uncompressed store text,
plus loads/dispatch and possible spills. All per-array offsets fit508 bytes;
actual branch ranges, clone extent, main frame and callers must be audited.
No handwritten assembly lowering is produced or treated as actual GCC output.

## Dictionary ROM And Stack

Flat5985*65*8=3112200B exceeds1MiB. Use exact64B value blocks, nine uint16
IDs per call, without call deduplication. Blocks0..7 cover output bytes0..511;
block8 has only8 actual bytes plus56 ROM-only zero padding. Compare all eight
words in each full block and one whole final word:65 reads, no padding reads.
Original full per-element failure fallback and counters remain unchanged.

A conservative analytic pool bound is available without running a model.
For each fixed seed/op/mode of the33 non-reduction/non-compress operations,
element value is independent of VL/start; the intersection of the active
interval with each block changes. Predicate and op19 restrictions can merge
but cannot add value patterns. The original interval boundaries give:

| Block | Result indices besides guards | Max interval patterns |
| --- | --- | ---: |
|0|0..14|7|
|1|15..30|2|
|2|31..46|3|
|3|47..62|2|
|4|63..78|4|
|5|79..94|2|
|6|95..110|2|
|7|111..126|2|
|8|127|2|

Sum26. For example block2 adds32..46; block4 has empty,63-only,full,64..78.
Thus at most33*3*3*26=7722 blocks for these ops. Reduction and compress each
have one start and at most7 VL values per seed/mode:2*3*3*7*9=1134 more.
Combined upper8856 (<65536), not a measured unique count. Pool566784B plus
107730B IDs gives674514B. Every future dictionary reconstruction must still
compare all520 bytes of all5985 calls against independently transcribed C.

Conservative planning envelope:674514 dictionary/IDs +8192 other rodata
(including2560B expected/32B input table) +12448 original backing/counters
+12288 reference runtime/log/HTIF +65536 text +4096 layout +65536 stack
=842610B, leaving205966B of1MiB. This is a stated reserve, NOT a linker map.
No per-call JSON or full flat gold is linked. Actual future map must retain
>=64KiB stack gap and account for all spills, clones, temporaries and alignment.

## Cost Boundary, Not An Execution Gate

Existing e32/m2 actual firmware2262610 is only an anchor, not m4 cost.
Its compiled upper2342335 contains FP257 instructions/call (128 cache LW+
128 SW and control), mask366030 and full33-word comparison/setup. Its actual
FW and static CFG are distinct evidence. Existing e64/m2 FP-period machine
paths are83/81/83 instructions for64 SD plus caller7; they are uint64/CAP32,
not an e32/m4 compiled bound.

With analogous scalar code, increasing output33->65 words adds roughly
32*(one SD+output LD+gold LD+branch)*5985=766080 instructions. Doubling
selected bitsets adds77175 assignments; four instructions per added bitset
(as in a plausible existing address/load/OR/store path) adds308700.
The FP period approach avoids a naive256 cache LW+256 SW refresh, but compared
with m2's257 it still needs256 SW+8 fresh table LW plus dispatch/caller work.
An e64-style282-instruction phase would add47250 across1890 calls.

Anchor arithmetic:2262610+766080+308700+47250=3384640, BEFORE new dictionary
address/ID work, changed RNG and spills. This is an analogy, NOT a lower bound
or measured m4 firmware. A constructive270-instruction leaf plus50 caller
allowance (320/call), four extra block lookups at six instructions each, and
20000 additional layout/control reserve gives an illustrative static-anchor
estimate2342335+766080+308700+119070+143640+20000=3699825. Neither the320
phase allowance nor the resulting total is an inspected GCC upper bound.

Conclusion: FP-period fresh-eight alone does not establish the inherited3M
reference gate or a <=3h DUT budget. ROM is analytically feasible, but COST
remains unadmitted. No compilation/reference experiment is proposed just to
hope that3M is met, and no timeout increase, oracle removal or prefix shortcut.
Any future authorization must first choose a narrowly justified scalar-cost
plan, then inspect actual full CFG, spill/caller/main changes and complete
source obligations before a single bounded reference. There is currently no
m4 Host/ELF/reference READY, runtime guarantee or DUT launch authority here.
