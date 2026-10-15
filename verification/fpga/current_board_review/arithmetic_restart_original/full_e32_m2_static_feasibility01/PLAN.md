# e32/m2 Full5985 Static Feasibility

Status: STATIC_ONLY_MEMORY_FEASIBLE_COST_HOLD. No model generation, Host,
compiler, Spike, DUT, RTL change, or live-job/active-trace query was performed.
The running e32/m1 task is untouched. This plan is not execution authorization.

## Source Identity

Archive: /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Original overlay/opt/ara-tests/rvv_matrix_e32_m2 and recovery22 rebuilt ELF
both hash978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c.
Original rvv_matrix_e32_m2.S:
f5a921e6cbb233c4e22f5431cfa198da50e8910d2644c66dd444b908cedebf07.
Original e32/operations.h:
2b3cce9dcdaaa6bc6e556ae4d2c013325ed48c473858c1984751c867a58f4b7b.
The recovery report states exact rebuilt ELF/disassembly equality; the C is
binary-equivalent reconstructed source, not proven original C bytes.
See SOURCE_PINS.json for the read-only actual hashes.

No existing full e32/m2 acceptance was found in the arithmetic review
READY/RESULT/TERMINAL and Markdown inventory. References to this ELF in other
shape READY files are recovery/source pins, not e32/m2 execution acceptance.
This bounded inventory statement is not a search of unrelated live jobs.

## Source-Derived Geometry And History

recovery22/reconstructed_oracle.c:10 selects uint32_t; :16-18 preserve
a[1024],b[1024],out[1026],mask[128] and counters. :94-128 define capacity,
RNG, seven VLs, masks, starts, every-call FP input replacement and output fill.
:138-168 define helper call, vstart, full result and guard oracle.
Original operations.h:36-41 gives35 operations, kinds and exact FP bit table.

Original .S:5 is e32,m2,tu,mu. At required VLEN1024, CAP64, vtype17,
physical2 registers per group,256B each for v8..9/v16..17/v24..25.
Capacity must be dynamically checked before any future acceptance.
Original ELF disassembly :737-752 gives capacity and op0:
capacity vset0112f557, full vset011772d7, target-VL vset0116f2d7,
vle32/vse32, vlm, scalar7, vstart write/read, exact target and return.

Original35 kinds are30 ordinary three-start operations and5 one-start
operations. Preserve3 seeds *7 VL *3 masks *(30*3+5)=5985 calls.
VL order is0,1,2,3,32,63,64. Starts are0,VL/2,and(VL<CAP?VL:CAP-1),
including duplicates; kind1/2/3 use only start0. Do not partition/reorder.

- Results:5985*64=383040 uint32 elements (1532160 bytes).
- Guards:11970 uint32 values, each0x0000005b (47880 bytes).
- Returned vstart checks5985; original helper instructions5985*13=77805.
- Output:66 uint32 words=264B=33 full scalar8B words. Positive-path oracle
  requires197505 complete8B reads; fill requires33 exact8B stores per call.
- Output byte0..3 is frontguard; bytes4..259 are64 results;260..263 rear guard.
  The first8B is frontguard+element0. The final8B at256 is element63+rear guard:
  it is NOT all guard, NOT a short2/4B tail, and NOT expendable.
- Typed fill is0x0000005b0000005b per SD, not byte-wide0x5b.
- Original backing remains4096+4096+4104 bytes. Only264 output bytes are
  initialized/read by the proposed packed positive path.
- Software mask128B; actual vlm atVL64 reads8B; upper120 software bytes0.
  There are2205 mask groups,735 per mode. Selected positions per mode64,32,9;
  original bitset assignments total77175. Reusing16 zeroSD would give35280
  zero stores, but actual compiled sites remain unbuilt/unmeasured.
- RNG performs64 xorshift steps per seed, with original overrides for every
  i%8, and restarts from the same seed formula. It is not a repeated/copied
 32-element m1 input. Source integer input assignments total552.
- FP calls1890, each64 iterations and128 uint32 source assignments, including
  VL0/no-op calls:241920 assignments. Retain fresh writes even when values
  equal the preceding call, and restore integer RNG setup on the next seed.

## Golden And Reuse Boundaries

Reuse the original e32 header's640 exact uint32 patterns=2560B, plus8 input
patterns. Never substitute host floating arithmetic. Same signed-zero,
NaN/inf/rounding bits and original fp_expected indexing. Larger CAP repeats
the8-entry pattern, not a larger FP table or exhaustive64 pairs per operation.
Original oracle covers data/guards/vstart, not fflags/frm result correctness.
Keep the normal bare-metal fcsr0 bootstrap explicit; no new per-call flag oracle.

The m1/m2 original .S texts are identical after replacing only106 LMUL tokens.
Read-only comparison of the458 original ELF helper instructions confirms106
vset differences (xor0x00100000),352 identical non-vset words. Preserve m2's
own original bytes; do not patch/reuse the m1 helper ELF or invent extra RVV.

Reusable: e32 integer semantics, exact FP table, original fallback, seed/op/
VL/mask/start nesting, memcpy-based scalar packing, generic lossless transport,
owner and fresh-lifecycle design. Must regenerate/derive:64-element RNG/gold,
VL/start boundaries, reduction/compress/slide/gather CAP bounds, mask coverage,
physical group2 join/length checks, full264B oracle, every FP128-write sites,
new actual ABI/scalar sites/stack/map and source/ELF pins. No fixed PC delta.
In particular b[2]=0xffffffff stays OOR, but b[3]=SEW=32 becomes a legal index
atCAP64 (it was OOR atCAP32). Slidedown source bounds likewise change to64.
Future target-owner requirement must be actual-model-derived, with only the
exact original vslideup.vi offset2/VL<=2 exception; no wholesale slide waiver.

## ROM And Stack

Flat5985*33*8=1580040B cannot fit1MiB even before text/BSS/stack.
Minimal proposal: exact64B value-block dictionary,5 uint16 IDs per call;
do not deduplicate, skip or reorder calls. Four full blocks cover bytes0..255;
the fifth stores the exact final8B plus56 representation-only zero bytes.
Only the first8B of that fifth block may be read from output.
Use4 unrolled8-word compare blocks plus one full8B comparison;33 exact memcpy
stores for output. Keep original mismatch fallback and original counters.

Static pool upper bound, without running the model:
For each fixed seed/op/mode of the33 non-reduction/non-compress operations,
the computed value at each element is independent of VL/start; only the
active interval intersection changes (the fixed predicate can only merge cases).
Across all original VL/start combinations, distinct interval shapes per
output block are at most7,3,4,2,2:

| Block | Element positions besides guards | Distinct interval shapes |
| --- | --- | --- |
|0 |0..14 |empty,[0,1),[0,2),[1,2),[0,3),[1,3),full |
|1 |15..30 |empty,full,16..30 |
|2 |31..46 |empty,31-only,full,32..46 |
|3 |47..62 |empty,full |
|4 |63 |empty,active |

Thus these33 ops contribute at most33*3*3*18=5346 value blocks,
deliberately overcounting equal sentinel/FP blocks. Reduction and compress
have only7 VL values and one start, hence at most2*3*3*7*5=630 further blocks.
Combined upper5976 blocks (<65536), pool382464B +59850B IDs=442314B.
This is an analytical upper bound, not a measured unique-pool count.
Later authorized Host must prove every reconstructed byte equal to original
gold for every call; no probability or presumed compression ratio is needed.

Planning allowance:442314 dictionary/IDs+4112 source rodata (including FP table)
+12448 backing/counters+12288 Spike log/HTIF+32768 text+4096 alignment/layout
+65536 stack=573562B, leaving475014B of1MiB. These are allowances, not an
actual m2 map. Retain original backing and verify >=64KiB actual stack gap,
all frames/temporary storage, alignment-safe memcpy and no output overread.

## Cost: Hold Before Compilation Or Reference

Memory fit is not a cost pass. Accepted m1 software02 has actual2472244
firmware instructions; compiled audit mandatory core2355885 and static upper
2550519. Its preserved FP loop has15 instructions/element. Doubling CAP adds
1890*32*15=907200 if that lowering is retained. FP-loop total alone1814400.

Retaining the analogous m1 bitset CFG gives approximately1347255 mask-bitset
instructions versus676935 (delta670320). This is extrapolation of existing
machine paths and source visit counts, NOT inspected m2 CFG. Selected-mode
counts and loop dispatch must be checked on any later actual compiler output.
33 output words versus17 add16 SD and16*(two LD+branch) per call:
16*4*5985=383040 with analogous unrolled lowering. Dictionary address/ID work
is extra; no saving from it is assumed.

Comparable-lowering core estimate:
2355885+907200+670320+383040=4316445 before unmodeled overhead;
actual-m1 anchor estimate2472244+same increments=4432804.
These are ~4.3-4.5M feasibility estimates, not universal lower bounds or a
guarantee for an uncompiled program. At the prior403.97instr/s projection with
20% margin,4432804 gives13167.7s, above10800s; this is not m2 DUT performance.

Conclusion: reuse of the unmodified m1 scalar lowering does not justify a
<=3M reference or <=3h DUT plan. Do not compile/run merely to discover that.
Any next software-cost proposal needs a separate narrow source-level proof,
e.g. reduce FP loop scalar address/modulo/branch work while retaining EVERY
128 input write each call. No such code is implemented or authorized here.
Do not hoist away FP refresh, shorten masks, omit oracle data/guards, weaken
the original fallback, substitute a prefix, add RVV, or raise time limits.
