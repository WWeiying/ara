# M5 Indexed-Overlap Pilot: Independent Static Analysis

Scope: existing completed pilot logs and current/frozen RTL only. No RTL change,
new simulation, wave conversion or fixture change. Exact cause remains unproven.

Latest evidence supersedes the earlier scalar-timeline interpretation below:
`failure_analysis01/WAVE_ADDENDUM.md` proves the AddrGen request starts at15,
advances to16, and faults there. Its oldEEW is32, indexEEW64, replay flags0,
with dispatcher v4/v5 tags32/64. See `DEDUP_REPAIR_REVIEW.md` for the resulting
specific static dedup defect and a conditional minimal repair review.

## Established Evidence

Pilot log: `vcs_candidate05_plan01/prepared02/pilot/tests/d32m2_i64_fault_ov1/work/run.vcs.log`.
Lines461..492 record one complete 8-word/lane capture, all 32 offsets correct.
Lines500..507 record only snapshot indices0 and1 replayed on queue8 (SlideAddrGenA).
At captured word4 the lane values are `17000,4000,11000,1e000` in hexadecimal.
Line508 reports check160 expected `0000000040017000`, actual `0000400040017000`.

The replay diagnostic at `lane.sv:603` prints every asserted snapshot-replay-valid
lane/queue, not only index0/1. Thus the visible capture/replay is not evidence
that every later retry also used this snapshot. Reconstruct its request epoch.

A small read-only scan of existing CSV found one io_gather entry (cycle357326),
21 handler entries, 16 repair-SFENCE entries, and 20 handler-MRETs. Four initial
handlers are syscall services. The final three handler entries occur at
cycles366479,367085,367690; preceding repair/MRET pairs are366972/367031 and
367578/367637. This is consistent with a later fault after16 successful repairs,
not an immediate index0 error. Tesla's full CSR timeline owns exact per-attempt
vstart and tval confirmation; do not infer the issuing vstart solely from the
reported exception element16.

Subsequent independent raw audit (`terminal_review02/PILOT_FAILURE.md`) reports
attempt16's architectural start at cycle367643 and accepted request at367681,
then actual mtval CSR=`0x400040017000` at367806, with vstart16 and other CSRs
correct. This excludes a fixture-print-only explanation. It also deprioritizes
the conditional start15-crossing scenario below; inspect the accepted RTL
request to confirm start16 and its v5 tag/layout selection. This document did
not independently decode all of those CSR rows or the target wave.

All six inspected worktree files match M5 frozen source bytes:

| File | SHA256 |
|---|---|
| ara_dispatcher.sv | `05e9a4633d3d3a989fc5433fbf647c26c9d21ec1837b210ee84b6c712f6815fd` |
| ara_sequencer.sv | `bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655` |
| lane/lane.sv | `5e621bf955cad43e87881253a2d8626c5bad23e2251e2ee7276a3518d1036241` |
| lane/lane_sequencer.sv | `c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc` |
| lane/operand_requester.sv | `327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2` |
| vlsu/addrgen.sv | `470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da` |

## Exact Wrong-Address Signature

NrLanes4 EW64 shuffle is identity (`ara_pkg.sv:533`). EW32 mapping
(`ara_pkg.sv:546`) maps sequential bytes4..7 to physical lane1 bytes0..3.
Consequently an aggregate physically containing EW64 indices16..19, incorrectly
deshuffled as EW32 and selected as a 64-bit index, yields:

```
index16 = 0x17000
index17 = 0x04000
wrong reduced_word = (0x04000 << 32) | 0x17000
base + wrong index = 0x0000400040017000
```

This exactly matches the observed tval, with no numeric fitting. It establishes
a strong layout-signature hypothesis, NOT which stage first introduced it.
An upstream wrongly repacked word can yield the same result with a correct
AddrGen old-EEW. A corrupted scalar base must also be excluded by the accepted
PE request, rather than assuming the base register remained correct.

## Request And Layout Chain

1. `ara_dispatcher.sv:4187` decodes index EEW64 separately from destination
   SEW32. At4236 old_eew_vs2 comes from the first active *index* register's tag:
   `eew_q[vs2 + active_first_register(eew_vs2,vstart)]`.
   The active source registers are v4 and v5 for VL32/e64 (v6/v7 lie outside VL).
   The active destination is only v4 for VL32/e32 despite destination LMUL2.
2. `:5342` detects mixed EEW across active index registers; `:5380` requests
   normalization for indexed mixed-layout sources. `:5415` postpones overlapping
   vd normalization while source normalization is required. `:5776` captures
   the index group before overlapping vd conversion.
3. Capture maintenance (`:1483`) is VSLIDEDOWN/stride0, source EEW64, VL32,
   no architectural destination. `lane.sv:510` saves raw VRF lane words, without
   deshuffling or repacking. Eight lane-local words cover all32 index elements.
4. Matching replay at `ara_dispatcher.sv:5575` sets replay_vs2 and **already**
   overrides old_eew_vs2 with source_snapshot_eew_q at5584. This exists in M5.
   It suppresses source reshuffle for that saved source, not every future load.
   Dispatcher snapshot-valid clearing at5920 is a publication event, not proof
   of lane RAM clearing or of corruption.
5. Backend/maintenance selection and the registered request are at`:193..213`.
   Non-segment `segment_sequencer` passes the request; its dynamic old-EEW
   overrides apply to store-vs1, not this load-vs2. `ara_sequencer.sv:775..795`
   copies old_eew_vs2, eew_vs2 and replay_vs2 explicitly into the PE request.
   No explicit downstream assignment replacing old_eew_vs2 with destination SEW
   was found on this static path. Check actual accepted structs, not transient
   combinational decode/debug prints during a maintenance request.
6. `lane_sequencer.sv:675..711` computes aggregate origin using index EEW64,
   then represents that range in the actual stored old-EEW units. With start15,
   first aggregate word3; with start16, word4. For oldEEW64 request starts3/4,
   ends8. For oldEEW32 it starts6/8, ends16. `scale_vl=1` is consistent because
   request vtype.vsew is also replaced by old-EEW. `operand_requester.sv:400..449`
   therefore computes the same physical word origin in both representations.
   Changing these counts blindly would alter correct alignment/token coverage.
7. Requester replay index is `vstart >> (3-eew)`; replay is selected only when
   ready and unstalled (`:518..539`). Lane substitutes snapshot RAM data before
   the operand queue (`lane.sv:494`), not at the final AddrGen input. Capture,
   queue acceptance, converted queue output and AddrGen acceptance are distinct.
8. `addrgen.sv:291..304` deshuffles by **old_eew_vs2**. It initializes selectors
   by **eew_vs2** at324..352, and at430..470 extracts the complete 64-bit offset
   and adds scalar_op. Destination SEW controls data-transfer size, not this
   deshuffle. Pointers advance only on the relevant accepted index handshake.

## Competing Falsifiable Explanations

**A. Actual request fields differ from the saved-source contract.** On the
failing request replay_vs2=1 with capturedEEW64, but old_eew_vs2=EW32 somewhere
between matching decode and AddrGen's latched pe_req_q. Locate the first change
using identical request ID/token and valid/ready; the existing5584 override
cannot simply be added again. An unchanged accepted oldEEW64 falsifies A.

**B. A later direct-VRF retry crosses registers with different physical layouts.**
Index16 is the first index in v5, whereas all32 destination elements occupy v4.
After destination conversion/writes, v4 may be physically EW32 while v5 remains
EW64. A request starting at15 can read its first active offset correctly under
EW32 and then concatenate index16/17 when it crosses into untouched v5. This
explains why the issuing vstart may be15 although trap vstart is16. It requires
proof of physical layout, tags, mixed-layout detection and absence/presence of
normalization on that exact retry. Static code should detect valid mixed tags;
therefore missing detection, incorrect tags, blocked-decode commit, or bypassed
request preparation must be demonstrated, not assumed. If start16 was accepted,
the first-active-register lookup should directly select v5's tag, narrowing B
to a bad tag or an incorrectly transformed v5 rather than simple boundary carry.

**C. Request EEW is right but operand ownership/repacking is wrong.** Replay or
VRF input is correct, yet queue output to AddrGen is different, stale, misaligned
or belongs to another request/maintenance epoch. Compare the same accepted word
through queue command EEW/count/conv/target, input acceptance, output, flush and
AddrGen selectors. If AddrGen's raw lanes and oldEEW reconstruct the expected
offset while idx_final_vaddr/tval differ, continue into base/MMU/exception staging.

The one early replay print does not choose A over B/C. Conversely, correct
capture proves that capture's bytes, not all later retries or metadata.

## Existing Wave First; Corrected Time Units

Correction: the initial version of this note incorrectly used a10ns clock and
recommended3.45M..3.70M ns. That recommendation and its assertion that the1M ns
cutoff misses the target are withdrawn. Independently checked:
`failure_analysis01/selected.vcd` header says100fs;
`ara_tb.sv:748` says ClockPeriod=1ns; `novas_dump.log:142` says
`-timescale=1ns/100fs`. Therefore console3574300000 means357430ns, not3574300ns.

The existing first1M ns dump need not miss the target; Tesla owns offline wave
decoding, so do not duplicate conversion or launch a new DUT run. Look around
357000..369000ns for the initial capture through the failed retry. Only if
required signals are absent, a separately authorized same-ELF/image capture
around350000..375000ns would cover initial setup,16 repairs and the first error.

Required discriminator signals (selected leaves/structs, not whole hierarchy):

- Dispatcher state/arch_decode/decode_blocked, CSR vstart/VL, eew_q/valid v4-v7,
  indexed_mixed_vs2_layout, reshuffle_req, source snapshot valid/EEW/VL,
  maintenance request and valid, ara_req / committed / d / o plus valid/ready.
- Sequencer accepted request token/id and issued PE request; AddrGen pe_req_i/q
  and lane registered pe_req. All need op, vstart, vl, eew_vs2, old_eew_vs2,
  vtype.vsew, replay_vs2, scalar_op.
- All four lane SlideAddrGenA request/cmd metadata, snapshot index/valid,
  VRF return, operand_queue input accepted and output accepted, target FU, flush.
- AddrGen raw lanes and valid/ready, deshuffled/reduced word, word_lane_ptr,
  elm_ptr, idx_op_cnt, idx_vaddr/final address and valid/ready; actual MMU
  request/exception and resulting vstart/tval.
- Actual VRF writes (address/BE/data/grant) to v4/v5 from both maintenance and
  VLDU, with IDs; distinguish physical completion from optimistic EEW updates.

No minimal RTL repair is justified until these discriminate the first bad stage.
In particular neither another5584 assignment nor initializing all metadata is a
supported fix from the present evidence.
