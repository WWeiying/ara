# Full22400 MACC Static Feasibility

**HOLD_FULL22400_FIXED_3M_SCALAR_FLOOR_EXCEEDED_NOT_RTL.** No equivalent full22400 cost plan was found in the MACC review subtree or the board-review static/cost/plan reports searched. Existing prefix482, selected singles/pairs and their launch/review documents explicitly exclude full22400. This report is static feasibility only, not source-port/reference/DUT readiness.

## Actual Source Identity

Use ../identity02/{report.json,reconstructed_oracle.c,scenario.S,operations.h,original.dis,rvv_integer_macc_accumulators_restart_e8_m4}. report.json proves complete rebuilt/original Linux ELF identity:
608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d.
Reconstructed C SHA is ab82b4891f9e926e37ef4d9f10fc44b0f953136deef2173b84427c0447e81006. Lost original C text SHA496a4ddb... is different; exact source-text recovery is false. Existing binary-equivalence proof, not current execution of the full Linux program, establishes this source's applicability.

The original archive is /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions42/binaries/rvv_integer_macc_accumulators_restart_e8_m4; archived S/header are under rvv_macc_restart_disjoint01. Small current source/ELF/disassembly hashes are recorded in STATIC_EVIDENCE.json. Original ELF is stripped; no symbol-size claim was fabricated from its empty readelf symbol output. Its LOAD headers give RX3600B and BSS3240B.

## Exact22400 Chronology And State

operations.h:9-22 sets8 ops,5 input seeds,5 accumulator trials, INTEGER_EXTENSION0, INTEGER_SCALAR_SUITE1, RESTART_SUITE1 and AGNOSTIC_POLICY0. The source loop at reconstructed_oracle.c:244-307 is:
seed -> op -> VL -> accumulator -> predicate -> start -> rm.

At VLEN1024, vlenb128 and actual helper vtype2=e8/m4 give CAP512. Seven VL values are0,1,2,3,256,511,512. max_start=vlenb*8-1=1023, hence starts are1,VL/2,VL,511 for all seven VLs. Do not deduplicate equal starts or remove VL0/no-work/alloff calls. INTEGER_EXTENSION0 and no FRACTIONAL_SUITE mean only rm0, not4 or8 rounding selectors.

5*8*7*5*4*4*1=22400 calls:4480/seed and4480/accumulator pattern. Full result bytes11468800, guard checks44800, low returned-vstart checks22400 and high return-container checks22400. Original mask groups5600 have four selected counts512,256,73,0; mode3 is real alloff. All eight vv/vx operators and all five seeds are necessary, not22400 repeats of vmacc.vv seed0.

The five old-vd patterns (source:29-39) are0,255,128, alternating even0x55/odd0xaa, and low8(0x937ad68de41c725f+0x9e3779b97f4a7c15*i), equivalently(0x5f+0x15*i)&255. They are freshly initialized on EVERY call (source:317-319); do not use all-zero old vd for the other four patterns. This is continuous architectural/CSR history, not cumulative old-vd reuse between calls: source explicitly reinitializes old vd each time. No reset between original calls or seeds is permitted.

Inputs use original xorshift13/7/17 and per-eight overrides (source:253-272). b[0] is additionally set at each seed to0,7,255,128,127, affecting vv as well as vx lane0. The helper's LB sign-extends these into t3; the target consumes the low8 bits. Do not replace LB with an unsigned64 return expectation or a constant0. Original a/b initialization is once per seed, NOT percall; the stronger accepted prefix482 adapter's extra fresh copies are an explicit scheduling adaptation.

## Original Oracle, Helper And CSR Contract

Source scalar_value:117-139,353-392 computes modulo256 for active i>=start && i<VL && selected(mask,i). Disjoint source headers enable neither alias-first/second nor chain steps:
- vv: old+a*b; old-a*b; old*a+b; b-old*a.
- vx: old+a*s; old-a*s; old*s+a; a-old*s, where s=b[0].
Inactive, prestart and tail bytes retain the selected old-vd pattern. AGNOSTIC_POLICY0 permits no all-ones relaxation. Both byte guards are0x5b. Fallback must count/report original per-element and guard errors; a packed mismatch alone cannot replace it.

Every original helper has13 instructions/50B (12x32-bit plus ret16-bit): full-capacity input A/B/old-vd loads, mask load, active-vtype setup, original scalar LB, vstart write, target, returned-vstart read, full-capacity setup and full output store. All291200 helper retirements remain, plus the separate3-instruction capacity helper. Original op0 is0x108c0..0x108f0, target0x108e0/b5042c57; the other seven actual target PCs/encodings are in STATIC_EVIDENCE.json. There are112000 original helper-memory instructions, with full-capacity memory calls even when the target is a no-op.

The original code reads vlenb once, writes vstart and reads it each helper, checks low32(vs)==0 and high32(vs)==saturation (0 here). Ordinary helpers return only vstart. They do NOT independently sample fflags, frm, vxrm or vxsat, and rm0 is an unused caller selector here, not proof of a rounding CSR. Preserve the original CSR/history; do not expand the status-container check into invented flag coverage.

The existing independent ../host_model.c explicitly rejects op!=0/calls>=482; ../full482_optimized_prepare01/model.py is also seed0/op0 first482 only. Neither is a ready all8-op/full22400 oracle. Actual source formulas are available, but a future full independent model would need all eight operators, all seeds/patterns and exact chronology. Nothing was generated or numerically evaluated here.

## Physical Geometry And Legal Packing

word=u8; original arrays are a1024B, b1024B, out1026B and mask128B, plus three64-bit counters and4-byte accumulator_trial (3230 nominal bytes before alignment; actual archived BSS3240B). m4 groups are v8..11, v16..19 and v24..27,512B each. The unused high512 input bytes remain original BSS zeros. Original helper out+1 loads/stores512B; guards are out0/out513. Checked output span is514B, NOT1026B, and output backing after513 remains outside that numerical oracle. Do not invent extra neighbor-register guards.

All128 mask memory bytes are initialized; vlm at CAP512 consumes64B, with the upper64 setup bytes zero. This does not prove an otherwise unobserved upper vector-register state.

Most optimistic legal scalar packing uses64SD plus one2B SH for514B fresh output, and64LD plus2B LHU for full readback. The inherited prefix instead performs65LD through out519 and ignores the final6 bytes; those bytes must not become new guards or oracle bits. Use legal aligned storage/memcpy, not an out+1 typed-pointer alias assumption. Tail alignment/BE/sign-extension and actual lowering still require future compile/Host proof if separately authorized.

The optimistic floor below even merges away the source's overwritten interior sentinel pass, charges no a/b or mask initialization, no comparisons, no setup loops and no golden loads. This deliberately grants savings beyond the stronger prefix adapter, making the HOLD independent of those choices.

## Instruction Floor Already Exceeds3M

No extra RVV, hidden memory-helper substitution, skipped freshness, checksum or omitted actual reads are allowed. RV64 scalar stores/loads cover at most8B per instruction.

| Unavoidable phase | Per call | Full22400 |
| --- | ---: | ---: |
| Fresh514B output, optimistically packed once |65 stores|1456000|
| Actual514B output readback, optimistically packed |65 loads|1456000|
| Exact original helper |13 instructions|291200|
| **Floor with ALL comparisons artificially free** |**143**|**3203200**|

This is203200 above3M BEFORE capacity/vlenb, returned-status/guard comparisons, gold loads, pointer/index/control, RNG/mask work, ABI/calls, logging/exit or failure handling. Therefore no dictionary/cache/sentinel/unroll tuning within the stated evidence contract can meet3M. Even granting zero-cost comparisons does not rescue it; this is a contract-specific ISA minimum, not a compiled CFG or a new numerical test result.

With the ordinary one comparison/difference operation per packed word, the floor is4659200. If inheriting the accepted prefix482 percall freshness of a512+b512+mask128+out514=1666B, there are208SD+SH=209 setup stores/call: the floor WITHOUT comparisons is6428800, and with65 comparisons is7884800. That stronger adapter contract must not be misdescribed as the original C's percall a/b initialization.

Original mask clear can at best be packed into5600*16=89600 SDs if preserving the clear phase; original selected-bit updates total1177400 SB assignments. Source RNG assignments plus scalar b[0] overrides total7365 before lowering/dead-store decisions. None is charged to the decisive3203200 minimum, and no claim of their actual future GCC counts is made.

## ROM, Stack And Wall Decision

Flat exact gold22400*514=11513600B, or prefix-style65-u64 rows11648000B, cannot fit a1MiB image. A possible dictionary layout is9 uint16 IDs/call (8 complete64B blocks plus2 valid tail bytes):403200B IDs plus64*U dictionary bytes. Do not read the62 padding bytes from the actual output or confuse them with guarded data.

Illustrative envelope, NOT a map proof:
403200 IDs +512 masks +5120 five-seed inputs +2560 five-pattern bytes
+4096 globals/alignment +65536 code/RO +16384 runtime +65536 stack
=562944+64*U. A1MiB image would need U<=7588 before any additional metadata/alignment; U and uint16 max index are NOT enumerated/proven in this static task. Loop parameters can remain computed, not require a22400-row descriptor table. The tableless original scalar oracle avoids the flat-gold ROM problem but cannot remove the mandatory-store/read/helper floor.

No transformed ELF/map/frame/stack proof exists for full22400. The archived Linux image's small BSS/code is evidence of source footprint, not a new SoC1MiB linker result. Full482's reserved64KiB stack is a layout precedent, not proof for a new transformation.

Existing full482 work05 reference reports835145 instructions, and its actual M8 full482 complete.json reports child0/2032.843667s. These are482-call, seed0/op0 and different-image evidence, not a full22400 M9 wall projection or acceptance. There is NO credible <=10800s full22400 guarantee, and the independent3M gate has already failed mathematically. Do not scale a short accepted control into admission, silently extend budgets, or apply a pending e8/m8-only6h discussion to this distinct e8/m4 MACC task.

Decision: retain full22400 as **NOT_ADMITTED/HOLD**, not an RTL bug or an accepted parent scope. No new arbitrary prefix, codegen, source port, Host, compiler, reference, DUT, raw scan or larger budget is proposed/executed. e8/m8 remains HOLD. Existing sealed evidence is unchanged.
