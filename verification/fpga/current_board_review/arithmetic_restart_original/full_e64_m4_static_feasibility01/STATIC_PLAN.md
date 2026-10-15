# Full original e64/m4: static feasibility

Status: STATIC_SOURCE_IDENTITY_VERIFIED; NOT_COMPILED, NOT_REFERENCE_TESTED,
NOT_DUT_ADMITTED. Date: 2026-10-14. Only small source/ELF/metadata reads,
hashing, instruction-byte matching and arithmetic were performed. No Host
equivalence run, model-generated gold, compiler, Spike, VCS, live query,
RTL edit or large trace read. Full 5985-call scope remains mandatory.

## Primary identity and historical status

Archive root C:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04`.
Review root A: `verification/fpga/current_board_review/arithmetic_restart_original`.

| Input | SHA256 |
| --- | --- |
| C/overlay/opt/ara-tests/rvv_matrix_e64_m4 | c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6 |
| A/recovery22/rvv_matrix_e64_m4 | c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6 |
| C/rvv_matrix_e64_m4.S | 197c07724fae208a10ef773f962d3f820d842d9449ad81b447121fdb52805b5f |
| C/e64/operations.h | bae4c627a4db226bd6a4a41601950aaf1401819933e9f568ce210a7c54922062 |
| C/manifest.json | 6cabb1e462113d3e4c26b29622c6abcfba7cbedbc52fe7b3bfc860678b8a8ce6 |
| A/recovery22/reconstructed_oracle.c | 7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91 |
| A/recovery22/report.json | b11efd30ec97318d8d4cb37468ae39fea7085f6235fd79a68589e2a6455b8266 |
| A/recovery22/rvv_matrix_e64_m4_decode/original.dis | d0cb511b8abc1523d4768e86e130efa025cb0f47ec0d5ef04d9fd52809bd0be3 |
| C/resume03_report.json | 618569f7d0086f05ede82c5f8993c67dc9ed5c634d97d66b642058af648cc94e |

Both ELF files are 11624 bytes and equal. Recovery reports exact ELF and
disassembly equality; original C text was NOT recovered. Its expected old
source hash is b2c21801fc8186d30fbe67d23f31bf5fb89dde1f838314e93c1224b6fdc58c44.
Use the byte-equivalent reconstructed C, not a claim of verbatim recovery.
Manifest compiler used -Os, rv64gcv/lp64d, freestanding, no builtins,
no tree/SLP vectorization, SEW=64. No software was rebuilt here.

Important: resume03 has this exact ELF `passed`, exit_code=0, 3.230812s,
`RVV_MATRIX_PASS sew=64 vlmax=64 cases=5985 elements=383040 errors=0 seeds=3
guard_tail_mask_vstart=checked`. This is historical board evidence, not a
new M9 run and not proof of a remaining historical arithmetic bug in m4.
The new objective is full contiguous source coverage on the chosen frozen
image; do not relabel the archived PASS as a failure or current-image PASS.

## Actual helper and geometry verification

Original ELF has capacity at 0x10892, bytes `fd52 57f5a201 8280`
(instruction encodings 52fd, 01a2f557, 8082). Its -1 AVL query selects
e64/m4, tu/mu. All 106 vector configuration instructions decode vtype=0x1a.
At VLEN1024: CAP=1024/64*4=64, each physical register holds16 u64 elements.

All35 helpers were matched as unique contiguous48-byte sequences in the
original ELF, in source order: 13 instructions each, first 0x1089a, last
0x10efa. Capacity3 + 35*13 =458 static helper instructions. Dynamic full
target-helper count is5985*13=77805, plus capacity3 once.

Common encodings in each helper (TARGET is the actual per-op instruction):
`01a772d7 02057407 0205f807 02067c07 02b78007 01a6f2d7 4e1d
00881073 TARGET 00802573 01a772d7 02067c27 8082`.
These load a/v8, b/v16, old output/v24 and v0 mask at CAP, select actual VL,
set t3=7, write vstart, execute target, read vstart, restore CAP, store vd.
Keep all13, including unused setup. No newly inserted RVV initialization.

Physical groups are v8..11, v16..19, v24..27, each512B; v0 is disjoint.
There is NO inter-group register overlap in this original helper. Preserve
the existing v24 old-destination dependency/tu/mu semantics; do not invent
an aliased-source experiment. Register boundaries are indices15/16,
31/32,47/48 and final63. Slide, gather and compress may move data across
these boundaries; use CAP64, not m2 CAP32 or VL, for gather/slidedown limits.
Reduction op22 uses seed v16[0] and defines reduced vd[0]; remaining original
output checks remain in scope. The FP targets contain no fused accumulate:
op25..34 are add, sub, mul, div, min, max, sgnj, sgnjn, sgnjx, sqrt.

Notable exact target bytes/PCs: slideup.vi2 38813c57/0x10c48,
slidedown.vi2 3c813c57/0x10c78, gather.vv 30880c57/0x10ca8,
redsum 00882c57/0x10cd8, compress 5e802c57/0x10d08,
masked load 00057c07/0x10d38, first FP 00881c57/0x10d68,
last FP 4c801c57/0x10f18. Future backend ownership must retain exact legal
empty slideup.vi2 qualification; no blanket slide or VL-positive waiver.

## Full original history and oracle

Order: seed0..2, op0..34, VL=[0,1,2,3,32,63,64], mode0..2, then trial.
Kinds0 have starts0, VL/2, (VL<CAP ? VL : CAP-1); kinds1/2/3 have one
start0. Thus 3*7*3*(30*3+5)=5985 calls:4095 integer +1890 FP.
Each seed has1995 calls, integer1365 then FP630. No reset partitions.
Final call ordinal5985 is seed2/op34/VL64/mode2/start63.

Seed RNG is original uint64 xorshift13/7/17, seeded
0x937ad68de41c725f XOR seed, with original per-eight-element overrides.
Generate all64 input pairs per seed, retain integer operations/order, then
all FP refreshes; restart RNG at the NEXT seed only. Carry all intended
architectural history across helpers. Modes select all/odd/i%7==2.
All128 mask bytes are cleared per original mode group,2205 groups total;
CAP mask load uses8 bytes and upper120 bytes stay zero. Do not replace
original RNG with m2 inputs or omit the unused portions of physical mask.

Full numerical checks:383040 result elements +11970 guard words;
5985 returned-vstart checks. Sentinel is uint64 0x000000000000005b,
NOT 0x5b5b... . Each call initializes/checks66 words=528B: guard offset0,
64 results offsets8..512, final guard offset520. No partial scalar tail:
last two words are full64-bit words. Across all calls:395010 fresh output
stores and395010 output reads,3160080 checked bytes. Typed values, all
prestart/masked/tail bytes and both guards must survive packing.

Keep original div0/signed-overflow/modular arithmetic, reduction, compress,
gather bounds and source failure counters/first20 diagnostic policy. A fast
word comparison must fall back to the original element/guard accounting,
not count bytes as distinct original failures or accept a checksum.
Original code checks returned vstart, NOT an fflags/frm oracle. Preserve
FP CSR history; do not add flag clearing or claim flags acceptance.

## FP table and periodic refresh direction

All640 u64 expected words match one exact ELF byte range: file0x1560,
VA0x11560,5120B, SHA ced4ecb4b7d1cfd206365c91712c955a4f4be5e8d6c73f54b7452c0e1491daa5.
The8-word input sequence SHA is110aafde28745fa6d8c08812c7c405ba640080a963fb132c99594018fb53a87c.
Its bytes occur five times; actual source table is file0x1520/VA0x11520,
bound by instructions103d0/103d6/103de and indexed loads10496/104b0:
0x11000+0x260+0x2c0. Do not select an arbitrary identical occurrence.
Exact original expected bits are used, not host floating arithmetic.

For EVERY FP call, including VL0, refresh a[i] THEN b[i], i0..63:
a[i]=inputs[(i+seed)%8], b[i]=inputs[(3*i+seed)%8]. This is128 ordered
u64 destination writes/call,241920 stores/1935360B total. Equal values or
consecutive identical calls cannot eliminate a store. Expected active
output comes from the original op/8x8 table, not an m2 dictionary.

The reviewed m2 direction can load the8 immutable input words afresh within
each call and select one of three seed permutations, repeated8 times for
m4. Preserve a0,b0,...a63,b63 order, through aligned typed stores or legal
8B memcpy with ordering constraints. No cross-call hoist, output prefill
from gold, or helper reset. All destination offsets0..504 fit signed12-bit
address offsets, but register allocation/spills are not yet compiled.
An illustrative hand-written leaf with8 LD +<=5 dispatch +128 SD +RET
would have<=142 instructions. This is NOT actual GCC lowering, a whole
refresh bound, or evidence of achieved savings. m2's64-store witness and
measured/software cost cannot be transplanted to this128-store shape.

## Proposed ROM, stack and cost gates

Flat full-output gold is3160080B, too large for a1MiB envelope. A64B block
dictionary needs9 IDs/call:8 full blocks +16 valid bytes in the ninth.
uint16 indices consume53865*2=107730B. The padded48 bytes of the last
dictionary block must NEVER be read from actual output. Check all66 actual
words, even repeated dictionary IDs; don't reuse prior-call read results.

Let U be the independently generated m4 unique block count. Dictionary
budget is64*U +107730 indices +384 masks +5184 original FP table/inputs.
U has NOT been enumerated here; m2's1282 blocks are not an m4 result.
Conservative proposed envelope preserves original24744B globals
(a8192+b8192+out8208+mask128+counters24), reserves65536B code/other readonly,
16384B runtime,65536B stack. Then total=285498+64*U; fitting1MiB requires
U<=11923, with actual alignment/extra metadata consuming remaining slack.
The uint16 index range must also be checked. This is a conditional layout,
not a ROM-fit proof. Do not put gold, all-call descriptors or large variable
arrays on stack. Original main frame is320B at0x102ca; that does not prove
the proposed frame. Future actual map/stack/ABI lowering must be inspected.
Use typed u64 or memcpy; no unaligned/alias-violating cast from output+1.

Original FP refresh loop10488..104bc has22 retired instructions/element:
64*1890*22=2661120 instructions for THIS PHASE alone. This proves why
blindly retaining the loop is costly, not a total firmware upper bound.
Even an ideal proposed scalar path has at least1109745 instructions for
target-helper windows,66 fresh stores/call,66 output loads/call and128 FP
destination stores/FP call, before capacity, gold loads, comparison,
branches, RNG, masks, wrappers or diagnostics. No new compiled/ref cost
has been measured. Neither bound proves a <=3h M9 execution.

Comparable accepted e64/m1 -O2 evidence, recorded in the existing m2 plan:
4528858 firmware /7544.534203s on M7 (~600 retire/s), CAP16. At that proxy
3M instructions would take~5000s and a10800s envelope~6.48M instructions,
but m4 has four times that group's data and different backend latency.
The e8/e16 m8 timeouts also forbid treating scalar retirement proxy as a
guarantee. No timeout/retry/new run is proposed or authorized here.

Next actionable step, only upon separate authorization: derive m4's exact
dictionary and independent original-C full5985 equivalence, compile one
scalar-only implementation, verify full helpers/no-extra-RVV/real map and
stack, then calculate actual success-path instruction cost before any
bounded reference. Retain all5985 calls if it does not fit: HOLD, not a
prefix, reset partition, smaller CAP or shortened FP refresh.

## Read-only directional dependencies

Under A:
`full_e64_m2_static_feasibility01/static_model.py`
SHA a5e776b86ef28738821ca8e3f6fc1676dde631348a161e7b3593362b391d0874;
`full_e64_m2_static_feasibility01/STATIC_PLAN.md`
SHA428dba919a39de0ef83f637709b7fd0cff21414a8dd4bb5230fcb4e0ee5e9eae;
`full_e64_m2_fp_period_source_proposal01/PLAN.md`
SHA f8aebf6fa2381f420521fe4f679a592165c79a54db0e7f0af7131c4345ce715d;
`full_e64_m2_fp_period_source_proposal01/fp_period.h`
SHA fb1386ff59ccd08e8f7803bdd1a12e9a3446459b9f9ea75e9a738da6d8d9de4c.
These were read, not executed or modified. This document supports later
full-scope preparation, not admission of this or the subsequent ten shapes.
