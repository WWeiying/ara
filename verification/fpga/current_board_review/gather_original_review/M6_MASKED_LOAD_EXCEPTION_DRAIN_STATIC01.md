# M6 Masked-Load Exception Drain: Static Finding

Static conclusion: the proposed wait cycle is supported by the frozen M6 RTL. This is a falsifiable candidate, not a measured DUT failure. No RTL/test/build/simulation or active CSV access was performed. Aquinas owns the joint experiment.

## Signal Chain And Escape Checks

Frozen root: `/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware`.

1. `src/vlsu/vldu.sv:612-696`: exception handling first drains partial VRF results through final grants. HANDLE_EXCEPTION pops only a valid mask head with the faulting owner, emits load done/burst exception, and decrements the issue/commit instruction queue counts. `:122-123,161` then gate incoming masks off when issue_cnt becomes0. The two-entry spill may still contain a word, but there is no continuing exception discard path.
2. `src/masku/masku.sv:1181-1224,1254-1277,1715-1735`: masked-load issue/read and commit counters advance through all expanded words; done requires commit_cnt0. Queue entries retain target/owner/first-element. Its queue depth is2. There is no load-exception, abort, or LSU flush input to MASKU (`:14-61` and `ara.sv:765-800`). Its running-vector AND with the global running vector at `:1099` does not independently abort the instruction.
3. `src/ara_sequencer.sv:551,1017-1021`: burst exception withdraws the broadcast and marks operand acceptance, but does not clear the MASKU PE running bit. That bit clears via MASKU done; global running is the OR of PE running, and ara_idle is its inverse (`:88,97-98`). Thus load done alone cannot release the mask VID.
4. `src/ara_dispatcher.sv:4383-4387,1239-1242`: masked-load exception enters WAIT_IDLE_FLUSH; LSU flush starts only after ara_idle. Flush propagates through lane sequencer/requester/operand queues to VLSU, then reaches the local VLDU spill. It is not an earlier escape from the mask wait. Reset would escape, but is not an architectural recovery mechanism. No independent timeout/abort bypass was found.

## Actual Minimum Boundary

Let W = (NrLanes * 8) >> data_EEW_encoding, in elements per expanded predicate word. For M6 four lanes: W=32/16/8/4 for e8/e16/e32/e64. Unit/strided loads substitute the instruction EEW into backend vsew; indexed loads use data SEW, not index EEW (`ara_dispatcher.sv:4157-4196`). Packed MaskM delivery is a separate 256-bit aggregate source beat and must not be confused with these expanded words.

For an accepted masked load with vstart<VL, A=floor(vstart/W)*W and N=ceil((VL-A)/W). MASKU initializes read/commit to VL-A and first-element to A. The precise discriminator is whether any of these N words remain unhandshaken to VLDU after its terminal exception cycle, with no successor issue context. Multiword alone is insufficient: accepting every word before issue_valid drops lets MASKU finish, even while local spill data waits for flush.

The spill is **two entries**, A/B, not one (`deps/common_cells/src/spill_register_flushable.sv:39-104`). If the fault is inside the first expanded word and no earlier whole-word pop occurred, at most two words can have been accepted: the exception pop does not make full-spill ready combinationally, and admission disappears next cycle. Therefore N>=3 is a discriminating sufficient boundary under those stated conditions. e16/vstart0 or2 requires VL>=33; VL64 produces4 words. Fault5 must be an active predicate element. All-off controls cannot create a page fault through this predicate-aware AddrGen. A VL>256 requirement would incorrectly demand multiple packed MaskM beats; it is not necessary here.

Measure the same VID: HANDLE_EXCEPTION and final grants, issue_cnt ->0, input valid/ready handshake count, spill A/B full and head owner/first-element, MASKU read_cnt/commit_cnt/queue count/head owner, MASKU PE done/running, ara_idle, dispatcher WAIT_IDLE_FLUSH and LSU flush0. Persistent remaining commit words plus mask PE running and no input handshake distinguish this candidate from a stalled VRF final grant, missing predicate source, or translation that never returns an exception.

## Minimal Owner-Aware Repair Candidate

After measured confirmation, a localized VLDU exception-only drain phase can retain the faulting instruction context **after prefix final grants but before the existing terminal queue pop/done**. Accept and discard only VFU_LoadUnit words matching that saved VID; pop matching buffered words until the final ordered word, identified by first_element+W>=saved VL, has been discarded. Temporary input absence is not completion. If the final word was already locally buffered, drain it rather than waiting for a new input. Do not acknowledge another owner, write VRF, issue memory, or force-clear the global mask VID. Terminal load done/exception acknowledgement then follow the existing path; natural MASKU done releases idle and permits the ordinary flush.

This keeps normal states/handshakes/queues unchanged and adds latency only to exceptional completion; verify normal-cycle equality rather than assuming physical timing neutrality. An unconditional ready, global early flush, or merely clearing MASKU running could discard another owner or release hazards while operands remain, and is not an equivalent fix.

Regression boundaries: N=1/2/3 and full-cap multiword; early active fault, word-boundary and last-word fault; vstart nonzero/aligned/unaligned; sparse predicates with inactive unmapped addresses and all-off no-trap; full prefix stores/VRF final grants, exact vstart/fault CSR and same-PC retry after remap; consecutive fault/retry and different-owner successor with no stale masks. Keep original full output/prestart/inactive/tail/guards and normal load/store/FOF controls. Cover both packed-input single-beat and multi-beat drain, and data EEW differing from architectural SEW or index EEW. No test change or production repair is authorized by this note.
