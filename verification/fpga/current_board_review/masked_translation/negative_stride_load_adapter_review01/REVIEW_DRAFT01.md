# Negative Stride Load Adapter Draft Review01

Status: PRE_READY_STATIC_REVIEW_NO_BLOCKERS_FOUND_NOT_ADMISSION.

Producer: `masked_translation/negative_stride_load_original01`.
This reviews existing fixture.c/S/h, observer.py, prepare.py and generated
software metadata/disassembly. READY was absent at review. No test, build,
reference or DUT was executed; no reference raw or running CSV was read;
no producer/shared helper/RTL was modified. Exact sealed admission remains
pending READY and a final code/pin comparison, not another raw traversal.

## Findings

No concrete blocker found in the reviewed draft. The target, original helper,
S/M transition, lower-page repair/refill, saved retry context and complete
numerical oracle agree with the authenticated source single. This does not
accept any reference result or DUT outcome, or the unfinished final pin set.

Informational accounting distinction: observer's `helper_retirements=11`
includes the Spike record for the faulting partial target and the successful
retry target. The helper has ten original instructions. A future VCS checker
must distinguish accepted fault attempt/exception from successful architectural
retirement, rather than blindly require eleven RVFI retirements. This is not
a fault in this reference observer's explicit expected record sequence.

## S/M And Page Geometry

- S entry uses base0x40001016 (=VA+4118), original six helper arguments,
  a4=64, and a5 pointing to the original signed -8 stride scalar. The original
  helper loads t3 from that scalar and preloads vd from output+1; source input
  is not substituted for the load's old destination.
- Sv39 root entry1 points to MID, MID entry0 to LEAF. Initially LEAF[0]=0,
  LEAF[1] maps the upper data page with flags0xc7. The separate root entry2
  is the aligned 2MiB identity mapping for firmware and stack. Thus S-mode
  target/code/stack are accessible while the lower target data leaf is invalid.
- Generated symbols place pages at0x80003000, guard_lo0x80002fc0 and
  guard_hi0x80008000. SoC BSS ends0x80008ac0; Spike BSS ends0x8000aac8;
  stack top0x800ffff0 lies inside the identity mapping. No address overlap
  with the two target data pages or page-table pages is implied by this layout.
- Exceptions are not delegated. Target runs in S, handler in M. Fault record
  checks mcause13, actual target PC, mtval=VA+4078 (=P-18), MPP=S/MPRV0,
  satp, VL8/vtype8/vstart5, fcsr117/vcsr5, marker0 and lower leaf0.
  This is an adapter CSR ledger, not Linux SIGSEGV or a Linux signal-frame ABI.

## Repair And Unchanged Retry

- Handler saves ra, t0..t6 and a0..a7 on a 16-byte-aligned stack; compiled C
  uses the normal callee-save ABI for s registers. Target base, destination,
  mask/capacity/stride-pointer arguments and t3 are restored before MRET.
- Fault snapshot stores v23/v24/v25 without loading them or writing v0.
  Observer checks saved prefix element2=0x287a, other pre-fault elements old91,
  and the declared additional snapshot controls. No software reconstructs vd.
- Lower PTE is installed, fence/SFENCE targets VA, `mx_refill_page` performs
  all2048 halfword original-value stores, then only source element2 at offset4102
  is XOR-poisoned to0x2821. Source element5 remains original0x26be.
- Snapshot vset temporarily selects cap64/start0. Handler explicitly restores
  e16/m1 VL8 and saved vstart5; fault branch does not change mepc. Actual MRET
  is checked against target PC, vector CSRs, MPP and original GPR arguments/t3.
- Retry retains baseP+22, not already-offsetP-18; AddrGen applies vstart5 once.
  Neither replay_0 setup nor vd/mask preload is repeated. Observer requires one
  helper entry, one capacity entry, exact original helper record continuity,
  two target records, and their active addresses VA+4102 then VA+4078.
- Successful helper immediately reads returned vstart0, restores capacity64,
  stores full vd and returns. Therefore post/helper-completion ecall records
  VL64, not VL8. Final ecall cause9 is separate from the one load fault13.
- Existing compile command metadata has rc0 and both tree/SLP vectorization
  disabled. Generated disassembly contains the intended explicit vector helper,
  snapshot and neighbor-seed operations; scalar refill/handler code does not
  introduce a replacement vector load of v0/v24.

## Oracle Coverage

Firmware checks actual vlenb128 and original capacity return64. It preserves
physical input128 (first64 initialized101+13*i, upper64 BSS zero), all128 original
offsets, output130 initialized91 and mask16 bytes0x24. Original helper's capacity
mask load consumes8 bytes; physical mask storage is not shortened to8.

Final checks retain all64 output halfwords, source guards output[0]/output[65],
returned vstart0, one fault, and all4096 data-memory halfwords with only P+6
poisoned. Observer independently maps byte-addressed values, requires every
expected byte present, and checks four ordered checkpoints covering pages,
page tables, guards, snapshots, physical input/offset/output/mask storage,
signed stride and fault/post/counter records. It checks each scalar comparison
call and matches its count to the firmware counter, not just a PASS string.

Additional output66..129 sentinels, v23/v25 neighbors, full fault snapshot,
intermediate whole-memory checks and fcsr/vcsr controls are explicit adapter
observations, not extra original Linux oracle fields or recovered history.
No new nonarchitectural timing constraint is requested by this review.

Final source scope is one independently failed single, zero predecessors;
not the parent96 sequence, its original Linux ELF execution, original signal
frame, or the429-record family. The source proof explicitly retains these limits.

## Draft Identity Only

These hashes identify the files read, not a sealed READY or execution approval.
All three fixture files equalled their generated prepared copies at review.

| File | SHA256 |
| --- | --- |
| fixture.c | 9739d5a839ca1f94e6be9fc1fa86d64cea9f2a27baa8ad8d7079c82f44cced2c |
| fixture.S | 98d7b1ca623ec196c554fc010d5211290b39ede476d4ad925be2ce1de4708488 |
| fixture.h | 2fed647c43d54092786d2a9851671b07b224a5d8b16a22707f3aa8f2c19485fb |
| observer.py | 3a9c17855ee618b82d03f83189277ec6ea3e0f50937a44ecf6b01281c6b25405 |
| prepare.py | 1e94b31f7513a5af39ea586f12f4ba2252297f9d30f73e2c84ddd72dbf0aa2c5 |

Generated source-proof ELF identities (metadata read, not execution by reviewer):
SoC `04e25a1fa3b6ba094af6d60d50f8ec0dd60f2ec2503f47dda05fd2011c5a0a43`;
Spike `19ec8c12d4b4f4a0974319a550bea7348d4dd890babcf1fe65afb90945abd60b`.
Producer host.json reports four positive checkpoints/21 rejected mutations;
this reviewer did not rerun them or independently certify a reference result.

Tesla was notified of this no-blocker draft finding and the record/retirement
distinction, and asked to notify READY sealing. Final review will bind actual
READY, code/metadata/pins and scope; no model polling or raw reference read is
needed for that static entry decision.
