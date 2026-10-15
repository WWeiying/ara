# e64/m8 Full5985: Static Plan and Budget Conflict

Status: source/ELF identified; current 3M software gate is incompatible with
the retained full scalar checking/store-history contract. This is NOT an RTL
failure. No Host, compiler, Spike, VCS, live-task query or RTL edit was run.
Only small archived source/ELF/disassembly/metadata and integer arithmetic
were inspected. STATIC_EVIDENCE.json contains actual identities and witnesses.

## Original Identity and Scope

Archive C: /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Review A: verification/fpga/current_board_review/arithmetic_restart_original.

- Original C/overlay/opt/ara-tests/rvv_matrix_e64_m8 and A/recovery22/rvv_matrix_e64_m8:
  SHA85a3dec84feba1068e1e27033f1f475c91df66dc88192dbaecdf44bf6b4df60b.
- C/rvv_matrix_e64_m8.S:
  SHA42c2fc99c38d1a37bad7b1def3833a3440a9d93de9b2ce69eb601b0b5368da10.
- C/e64/operations.h:
  SHAbae4c627a4db226bd6a4a41601950aaf1401819933e9f568ce210a7c54922062.
- A/recovery22/report.json proves exact reconstructed ELF/disassembly equality;
  A/recovery22/reconstructed_oracle.c is binary-equivalent reconstruction,
  NOT a claim that the lost original C text was recovered verbatim.
- C/manifest.json and A/prepared01/original_identity.json give the actual
  original -Os/SEW64 build provenance. No rebuild was performed here.
- C/resume03_report.json records this exact original as board PASS/exit0,
  4.064690199680626s, CAP128/cases5985/elements766080/errors0.
  Historical board PASS does not imply current frozen M9 full-scope acceptance.
  All22 original shapes remain the objective; do not substitute this old PASS.

The actual capacity bytes select vtype0x1b=e64/m8, tu/mu. All106 original
vsetvli instructions agree. At VLEN1024, CAP128 and physical groups are
v8..15/v16..23/v24..31 (1024B each); no v32 neighbor is legal.
All35 distinct48B helpers uniquely match the actual ELF in source order:
13 instructions/helper, capacity3 plus35*13=458 static instructions.
No extra RVV initialization/checker is proposed.

Chronology remains seed0..2, op0..34, lengths0/1/2/3/64/127/128,
mode0..2, then original trial starts.30 operations have three starts and
five have one: 3*7*3*(30*3+5)=5985, comprising4095 integer and1890 FP.
Full results766080, typed guards11970, returned-vstart5985, helper77805.
Do not reset between original helpers, collapse repeated VL0 calls or
replace full5985 with a prefix. Final call is seed2/op34/VL128/mode2/start127.

## Complete Data and Model

Each call fresh-initializes and checks130 u64 words=1040B:
guard0,128 results at offsets8..1024, guard1032. All778050 output reads
and stores remain actual; neither short tails nor checksum acceptance.
Sentinel/guards are uint64 0x000000000000005b, NOT byte-fill5b.
Original backing arrays remain a8192B+b8192B+out8208B+mask128B+counters24B.
Only the low1024B input groups are business-initialized; preserve remaining
backing zeros and exact ELF BSS/bootstrap/ABI rather than inventing guards.

Original RNG is xorshift13/7/17, seed0x937ad68de41c725f XOR seed, with
original per-eight-element overrides; initialize CAP128 pairs anew only at
the next original seed. Preserve div0/overflow/modular arithmetic, gather
CAP128 rather than VL bound, reduction seed and compress chronology.
Failure slow path retains original element/guard counters and first20
diagnostics, not per-byte failure inflation.

All128 mask bytes are zeroed for each of2205 original mode groups.
Legal scalar widening can preserve that zero-clear as16 ordered SDs, without
new RVV/fence; original bitset SB sequence stays unchanged. Selected counts
at CAP128 are128/all,64/odd,18/i%7==2, giving
(128+64+18)*(3seeds*35ops*7lengths)=154350 bitset SBs.
Helpers actually vlm16B; physical upper112B must stay zero.
Do not substitute m2/m4 selected counts or omit full128B clearing.

Original FP expected table is640 u64/5120B, uniquely byte-matched in this
actual ELF; its offset/VA/SHA are recorded in STATIC_EVIDENCE.json.
The eight input words are bound to actual original VA0x11520 by the
LUI/ADDI/spill/indexed-LD chain, not an arbitrary identical byte occurrence.
Use these exact original bits, no host-float recalculation.
EVERY one of1890 FP calls (including VL0) refreshes a[i] THEN b[i],
i0..127:256 u64 stores/call,483840 total. Values follow
inputs[(i+seed)%8] and inputs[(3*i+seed)%8].
A legal eight-period scalar clone can load eight original table words anew
percall, choose the actual seed permutation, and emit16 repeats of16 ordered
SDs. Equal values do not excuse missing writes; no cross-call hoisting.
Actual lowering/PC/64bit bank-order/store ownership must later be proven.
Original source has no explicit fflags/frm oracle; retain CSR history without
inventing a flags acceptance claim.

## ROM and Stack Proposal

Flat gold=5985*1040=6224400B, unsuitable for a1MiB image.
Use17 dictionary blocks/call:16 full64B blocks and16 valid bytes in block17.
uint16 IDs cost203490B. Last block output offset1024 has final result at1024
and guard1032; never read its48 padding bytes as output.
Every real130-word read still occurs even for repeated block IDs.
Unique block count U is NOT enumerated here and ROM fit is not yet proved.

Conditional total envelope:
64*U +203490 IDs +384 mask tables +5184 original FP inputs/table
+24744 original globals +65536 code/other RO +16384 runtime +65536 stack
=381258+64*U bytes. Fitting1MiB requires U<=10426 before extra metadata and
alignment; uint16 maximum index also needs proof. Existing smaller-shape
dictionary counts are not an m8 result.
Original main frame is320B (PC0x102ca); future transformed frame/stack map
must be measured, not assumed equal. Keep gold/IDs/descriptors off stack.
Aligned u64 stores/loads or builtin memcpy are legal; no out+1 alias cast.

## Why the Current 3M Gate Cannot Admit This Contract

These are minimal RV64 scalar instruction counts, NOT an actual GCC CFG
upper bound or measured firmware. Each listed memory operation must execute,
and complete per-word exact scalar comparison needs at least one equality/
difference operation per64-bit word (no added RVV or lossy checksum).

| Required phase | Instruction floor |
| --- | ---: |
| 130 SD fresh output/call | 778050 |
| 130 LD full output/call | 778050 |
| 130 scalar compare/difference operations/call | 778050 |
| 256 SD original FP input/call,1890 calls | 483840 |
| 16 SD full mask clear/group,2205 groups | 35280 |
| Original ordered bitset SBs | 154350 |
| 13 original helper instructions/call | 77805 |
| Total | 3085425 |

This exceeds3M by85425 BEFORE gold loads, pointer/index/loop instructions,
RNG/seed setup, argument/JAL wrappers, vstart checks, bootstrap/return,
dictionary lookup or failure fallback. Therefore no compiler tuning can
make this retained contract fit3M. This is a contract-specific floor, not a
universal theorem about all possible differently authorized test designs.
Mask-write replacement or dropping in-firmware comparisons would change
the stated contract and is neither proposed as equivalent nor authorized.

The untouched original FP loop10488..104bc alone has22 instructions/index:
128*1890*22=5322240, so it cannot fit either. The periodic clone is useful,
but cannot erase the required483840 FP stores or3085425 overall floor.

## Explicit Budget Decision Needed

No new time/instruction authorization is fabricated here. Keeping3M means
this full-scope source-port is ineligible, not a silently pending RTL bug.
For later user choice, the smallest sensible next step is separately
authorized software/Host/compile/layout/CFG preparation under a revised
instruction gate, still with no reference/DUT until actual CFG is assessed.

Directional cost only: accepted e64/m2 software02 actual CFG upper2330297
and reference firmware2263782 are smaller-shape evidence. Growing the listed
required phases CAP32->128 adds2201955 instructions; mechanically adding
that to the m2 upper gives4532252, NOT an m8 upper bound. Extra dictionary/gold
loads and lowering overhead can raise it further; a4.5-6M planning band is
reasonable for discussing resources, not an admission guarantee.
At the existing conservative403.97 instructions/s proxy plus20percent,
4.5-6M projects roughly13367-17823s (3.7-5.0h), outside a3h case.
Different m8 backend latency can make it worse; no actual m8 wall time was
measured here. Do not silently extend10800 or run until timeout.

Choices for the user/main are thus explicit: retain the gate and classify
this shape as not admitted, or authorize finite software cost proof followed
by a separately chosen larger reference instruction bound and DUT case
budget based on that proof. Neither choice permits shrinking calls/results,
substituting historical PASS controls, resetting original history, or
counting this static report as M9 acceptance.
