# Negative-Stride Store Source And Reference

Status: **REFERENCE_CHECKER_PASS_NOT_DUT**, own bounded executor/observer;
independent review pending. No RTL/image build, DUT/service launch, reference
retry or old sealed-file modification. Scope is one original failed source
single, no invented predecessors and not the original96-case Linux parent.

## Identity

Archive root `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01`;
single suffix `e16_m1_u1_s1_b3_m2_f0_g3`.

| Input | SHA256 |
| --- | --- |
| Archived diagnostic ELF | `07d285218316422ea69480c764c09fe17e7ebca6a49e31c5abc7e4ff6cae5578` |
| Original C | `5ece6a9e216d611b4b62823d037b9b3f35304b952fb693375b86e8d79d023c4d` |
| Original assembly | `597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039` |
| New SoC ELF | `bdeaefcb2a25106578d2c78ca4bcb30f634dc73db9a4be03ac1607f2989235fb` |
| New Spike ELF | `c43a8d22b28db2ba89d8b46d6cd9aa2ccc17a887f891c54ef85af64d92492253` |
| Actual full reference raw | `30549f781ff2ae2d6c7fc2b12e14c74a5a82924e31b85faa7e517f8ac06ac75b` |

`software01/source_proof.json` compares actual archived ELF instructions:
capacity0x109fa/3 instructions, unused load0x10a02/10 and store0x10a28/10.
All match both new backends byte-for-byte, including original store target
at0x10a3c,09c55c27. The linked original.S was copied unchanged. Both helpers
remain present; reference execution of any unused load-helper PC is rejected.

Historical single report is exit1/errors1/handler_errors1: P-2/start3 instead
of P-18/start5. There is no independently established historical data error.
The selected diagnostic is `single_current_oracle_trial`; the archive does
not establish per-trial equivalence to the uninstrumented original parent's
aggregate. A real measured single and a byte-identical parent are different
claims. Source hashes and case.json remain pinned without changing that scope.

## Once-Only Reference

The non-ZCC existing golden used exactly
`rv64gcv_zfh_zvfh_zvl1024b --priv=msu --pmpregions=0 -m2 --instructions=1500000 -l --log-commits`.
Before running, compiled-path1250000-instruction estimate and raw sizing
245888608 bytes admitted the fixed1500000-step/120s/256MiB limits.
`software01/bound.json` and finalized checker/Host hashes were pinned first.

- Actual Spike child wait: **0**,12.753124533s, no timeout,103533239 raw bytes.
- Actual executor/observer wrapper wait: **0**,35.752825583s.
-858376 commit-format records, of which858371 are firmware instructions.
-17275 actual scalar comparisons, all equal, plus independent byte-map checks.
-One capacity entry, one store-helper entry, two target attempts, one fault,
  one S-mode completion ecall, and HTIF1 (software exit0).
-Inputs rehashed unchanged before and after. `execution.json` was persisted
  before the full raw observer, not reconstructed from its PASS result.

The actual returned status and numeric waits are in
`reference01/{status.json,execution.json,wrapper_wait.json}`. Full raw remains
`reference01/spike.trace`; no second reference or alternate raw was used.

## Actual Store And Retry Evidence

`P=0x40001000`, original baseP+22, stride-8, VL8, vtype8, mask0x24.

| Event | Firmware record | Actual observation |
| --- | ---: | --- |
| Initial full checkpoint |160125| original setup/data/pages/guards |
| First store attempt |160172| PC80000e12, start0, only VA40001006=P+6, value127 |
| Fault observation |before272235| cause15, same target PC, tval40000fee=P-18, VL8/vtype8/start5 |
| Early scalar prefix read |before checkpoint1| LHU at8000051a reads127 before snapshot fence/page repair |
| Fault full checkpoint |272235| source v24 unchanged, completed prefix127, lower leaf invalid |
| Repaired full checkpoint |563294| lower2048 halfwords refilled, P+6 poisoned to36 |
| Actual retry MRET |563333| mepc80000e12, MPP=S, VL8/vtype8/start5, original arguments |
| Second store attempt |563334| same PC, start5, only VA40000fee=P-18, value166 |
| Final full checkpoint |850613| P+6 stays36, P-18 is166, all other memory/oracle checks pass |

Actual MRET a0=40001016, a1=800083a0 (input), a2=8000819a (output+1),
a3=80008188 (mask), a4=40 (cap64), a5=80001180 (stride storage),
t3=fffffffffffffff8. Base is **not** changed toP-18 before vstart5 resumption.
The original helper is not re-entered and source vd is not reloaded on retry.

Snapshot/full-memory phases compare23244/23236/23236/23228 bytes. They cover
all8KiB data and page-table neighbors, all source input/offset/mask storage,
saved source/register neighbors and output guards. The independent observer
starts from real ELF PT_LOAD bytes; startup must write every required BSS byte.
All retired firmware PC/encodings, actual target store values/addresses, action
ordering, real MRET CSR/GPR context and final CSR restoration are checked.

`helper_retirements=11` counts Spike commit-format records, including the
faulting partially executed store plus its retry. It is **not** a claim of
eleven architecturally retired helper instructions in RVFI. The original
helper has ten instructions; any future DUT checker must handle that distinction.

## Original Oracle And Host Negatives

Physical input128 initializes only first64, offsets128 and mask16 retained.
Output130 initializes typed halfword0x5b. All64 returned store-source elements
equal101+13*i, including inactive/tail positions. Guards are output0/65;
extra physical slots66..129 are supplementary sentinels, not extra original
results. Four whole4096-halfword memory checks include the original final
logical-element search. No partial memory/output oracle substitutes for them.

The C Host oracle and separate Python arithmetic agree on17152 rows.
41 negative controls reject wrong historical tval/start, missing committed
prefix, inactive memory write, changed saved store source, missing poison,
bad refill, replayed prefix, wrong element5, wrong output/tail/guards,
PTE neighbor, unused input/offset corruption, post-vstart/fcsr, missing byte,
double-adjusted retry base, wrong stride/arguments/privilege/PC, load instead
of store, extra target attempt or missing/wrong target writes. Actual compiled
symbols and09c55c27 are checked, not synthetic nonexistent ELF fields.

## B Response And Scope Boundary

Original handler's committed-prefix visibility check remains explicit and
stronger in placement: the marked scalar load precedes snapshot fences and
remap/refill. Correct target data must be architecturally visible before the
fault handler observes it; poison must survive retry. The observer verifies
this from actual stores, reads and full checkpoints.

**Spike does not model AXI B responses.** No pending-B timing, forced bus stall,
or exact RTL handshake proof is claimed. Those belong to later M6 DUT evidence
if authorized. Existing VSTU B-drain and source-coordinate hypotheses are not
declared bugs or repaired merely because software reference passes.

The Linux mapping/signal frame is replaced by genuine Sv39 S-mode accesses,
an invalid lower leaf, M-mode architectural observation, leaf repair/SFENCE,
refill/poison and same-PC MRET. Original initialization/helper/numeric oracle
remain, but this is not Linux SIGSEGV/sigreturn equivalence or original96
history acceptance. No DUT worker/image was prepared or launched this turn.

## Qualified Future Cost

Measured858371 firmware instructions versus the adjacent load's836971 and
996.680s M6 time suggest about1022s at that proxy, not a prediction of store
bus timing. The deliberately slow273/s proxy plus20% gives3773s (63min),
below3h. Neither estimate guarantees a pass or authorizes a DUT timeout.
Independent source/reference review is the next gate.
