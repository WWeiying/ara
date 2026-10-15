# Negative-stride STORE single entry review

Decision: **ACCEPTED FOR WORKER PREPARATION, REFERENCE ONLY; NOT DUT PASS.**
No blocking input/source/oracle/ELF/reference-receipt finding. This review does
not authorize a DUT launch or claim original Linux signal/parent closure.

Input READY: `../negative_stride_store_original01/READY.json`, SHA256
`af47366282d50441056b62740801f754615b31eec82f35083b538bade7a61f65`.
All following source/checker line references are relative to that producer.

## Actual source identity

Exact single: `rvv_small_fault_strided_negative_stride_e16_m1_u1_s1_b3_m2_f0_g3`
under `ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01/singles/`.
Tuple is unmapped1/store1/boundary3/mode2/split0/gap3, e16/m1, NF1, VL8,
capacity64. Original initialization, active predicate and full final oracle
are retained in the real-Sv39 port; original helper assembly is unchanged.

| Original artifact | SHA256 |
| --- | --- |
| scenario.c | 5ece6a9e216d611b4b62823d037b9b3f35304b952fb693375b86e8d79d023c4d |
| scenario.S | 597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039 |
| scenario.elf | 07d285218316422ea69480c764c09fe17e7ebca6a49e31c5abc7e4ff6cae5578 |

Provenance distinction, not a blocker: case.json's input-side measured_trial
has PC68172/0x10a4c. The actual independent single result is
`evidence/single_board_report.json:17710`, results[75]: PC68156/0x10a3c,
exit1, errors1, handler_errors1. That PC matches the archived ELF target.
Its actual fault is P-2/start3 instead of P-18/start5. The input-side record
must not be misrepresented as this single's actual ELF execution. The matching
`single_symptoms.json` records the same normalized address/start failure.
This is `single_current_oracle_trial`; the original parent rebuild is explicitly
not byte-identical. No separate historical memory-data error is established.

## STORE semantics, not LOAD substitution

Original formulas give base P+22, stride -8, mask0x24, active elements2 and5.
Element3's P-2 is masked off and must not fault. Element5's P-18 must fault
with cause15, VL8/vtype8/vstart5 at the store target.

- `fixture.h:18` retains the original logical-element search and final whole
  memory oracle. Unlike LOAD, source v24 and all64 output elements remain
  input[i]=101+13*i; inactive/tail source values are not 0x5b.
- First attempt writes only P+6=127. `fixture.c:78` and `observer.py:161`
  explicitly observe this prefix before snapshot fences or repair, requiring
  both the actual write and the scalar LHU result.
- `fixture.c:84` installs the missing lower leaf, SFENCEs VA, refills all2048
  lower-page halfwords with the original formula, and poisons P+6 to36.
  Full checkpoint2 observes these changes before retry.
- `observer.py:104` requires same-PC MRET with base still P+22, t3=-8,
  original six arguments, S privilege, VL8/vtype8/vstart5. No helper re-entry,
  source reload, or pre-adjustment of base to P-18 is permitted.
- `observer.py:109` permits exactly one write per target attempt: first127
  at P+6, then166 at P-18. Extra/masked writes, load effects and prefix replay
  fail. Final P+6 must remain36, and all other8KiB bytes keep their oracle values.
- Full source output64/two original guards, supplementary allocation
  sentinels, v23/v24/v25 snapshots, input/offset/mask storage, page tables and
  neighbors are retained. Four4096-halfword checks are not partial sampling.
  CSR checks preserve fcsr117/vcsr5; this fixture also contains actual final
  restore readbacks at `fixture.c:143`, rather than relying solely on writes.

The mature LOAD observer was compared directly with this STORE successor.
The changes correctly switch cause13 to15, select replay_1/fault_1_pc, reject
the entire unused LOAD window, preserve store-source registers, and add actual
write-value/address and early-prefix checks. LOAD reference PASS is not being
used as STORE evidence.

## Checked evidence

All66 READY pins were independently hashed, including a streaming hash of the
raw file without parsing it. All54 pre-reference input pins match READY.
Source-proof helpers were independently checked against actual PT_LOAD ELF
bytes: capacity3, load10 and store10, in both SoC and Spike binaries (six
windows). Target instruction is09c55c27, not09c55c07.

Actual durable receipts: Spike rc0, timeout=false,12.753124533221126s;
executor/observer wrapper actual wait0,35.752825582865626s. The executor writes
execution.json before parsing. Exactly one initial reference attempt is
recorded, with no retry or not_completed result and no pre-reference checker
delta. Limits remain1500000 instructions/120s/256MiB; actual raw103533239B.
Profile is `rv64gcv_zfh_zvfh_zvl1024b --priv=msu --pmpregions=0`.

Bound reference result records858376 commit-format records,858371 firmware
records,17275 scalar comparisons, one helper entry, two target attempts,
one store page fault, one S-ecall, HTIF1. Four checkpoint byte counts are
23244/23236/23236/23228. Target PC is0x80000e12; retry MRET immediately precedes
the second target event. All recorded scope/receipt/command/hash fields agree.

Existing Host executable output was independently compared with original
arithmetic: all17152 rows agree. The41 recorded focused negatives and their
code cover historical tval/start, source/tail/guards, missing/extra/masked store,
prefix visibility/poison/replay, refill, PTE neighbors, retry context and CSR.
No Host executable or negative suite was rerun.

Independent metadata/source/ELF/Host-output verification: inline `python3 -B`,
tool chunk `1c53c5`, actual exit0,2.554108965s. It did not import the producer,
parse reference raw, compile, or launch anything. Original sealed files remain
unchanged. Full raw architectural correctness relies on the reviewed sealed
observer plus its bound completed result; this is not a second independent
full-raw acceptance pass.

## Handoff boundaries

SoC ELF: `../negative_stride_store_original01/software01/soc.elf`

SHA256: `bdeaefcb2a25106578d2c78ca4bcb30f634dc73db9a4be03ac1607f2989235fb`.

Spike ELF SHA: `c43a8d22b28db2ba89d8b46d6cd9aa2ccc17a887f891c54ef85af64d92492253`.
Source-proof SHA: `d2447c19706ec08a88ee1079bae169eefdf594a42ac2306dca468bae6b72f44e`.
Reference-result SHA: `d17087877281d300e7a2f1621fdc4daf05cd2349bc28d880be567afa1e57f875`.

Future DUT checks must retain the whole oracle, cause15/P-18/start5, prefix
visibility, remap/refill/poison and same-PC retry. Spike's11 helper records
include the faulting partial attempt plus retry; do not require11 architecturally
retired helper instructions from DUT RVFI. Original helper length is10.
Spike has no AXI B channel: this reference does not prove delayed-B behavior,
bus completion or a current RTL repair. It also does not replay Linux
SIGSEGV/sigreturn, original96 history, or accept other shapes/strides.
