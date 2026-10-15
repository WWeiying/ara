# Actual Consumer Review

2026-10-10. Read-only RTL review; no consumer simulation by this reviewer.
This file is independent of Aquinas's repair review and Sv39 fixture.
Parent-reported final04 large-offset six original-source PASS is unrelated
evidence, not masked-translation acceptance.

## Blocking Consumer Findings

1. **VLDU exception completion does not establish final writeback.**
   `hardware/src/vlsu/vldu.sv:615` enters exception handling on the terminal
   descriptor. `:627` marks the partial write slot valid, without adding it
   to result_queue_cnt. `:631` waits only for the current read slot's request
   valid bits to clear; it does not require all occupied slots to drain or
   `result_final_gnt`. `:643` then signals done. In contrast normal completion
   at `:550` explicitly distinguishes requester acceptance from final grants.
   `operand_requester.sv:117` buffers load results, and `:172` reports the
   downstream grant separately. Concrete discriminator: fault after a partial
   active/skip word, accept every load result into requester buffers but delay
   bank grants. The exception FSM can retire before those prefix writes finish.
   With older full words queued, the read slot need not even be the partial
   write slot. An ordered AddrGen marker alone does not fix this existing path.

2. **VLDU exception cleanup leaves incomplete accounting.**
   `vldu.sv:638`..`:668` resets AXI pointers and decrements instruction counts,
   but does not zero remaining issue/commit bytes, discard/retire the partial
   result entry coherently, or release the current mask. `idle_o` at `:742`
   requires those counters, result occupancy/valids and mask valid to be zero.
   The delayed `lsu_ex_flush_q` only flushes the mask spill (`:103`); it does
   not reset those counters. For first-element fault on a nonempty load, no
   normal byte progression has occurred: remaining bytes survive HANDLE_EXCEPTION.
   A younger acceptance may overwrite some state, but that is not a valid
   cleanup contract. FOF must complete internally even when no trap is taken.
   These are static counterexamples, not new measured full-system failures.

3. **A new ordered local fault must not also use VSTU's early-error path.**
   `vstu.sv:544` latches either illegal-store or an exception at the FIFO head;
   `:578` can then discard the issue instruction once pending B is zero and it
   is the only committing store. `:600` acknowledges ANY current descriptor,
   not specifically an exception. If an early sideband accompanies an ordered
   marker behind skipped prefix tokens, it can pop the wrong token and drop
   required source/mask progression. The candidate suppression below addresses
   this producer-side hazard; retain a real-consumer check with queued prefix.

## Skip Geometry and Mask Lifetime

Let E=1<<vsew, B=NrLanes*8, W=B/E, first=floor(vstart/W)*W.
MASKU aligns the first memory mask window down (`masku.sv:1085`, `:1813`),
publishes owner and `vl-read_cnt` at `:1208`, and advances W elements per window.
The window is not packed to begin at vstart. Consumers initialize byte pointer
to `(vstart*E)%B`, remaining bytes to `(vl-vstart)*E` (`vldu.sv:676`,
`vstu.sv:645`), and release their held mask at word boundary or instruction end
(`vldu.sv:438`, `vstu.sv:474`). Example: e16, four lanes, vstart15/VL18 consumes
two bytes of window first0, releases it, then consumes four bytes of first16.
Do not emit prefix skips for elements0..14 or acknowledge each element's mask.

AddrGen must inspect the consumer's exported spill head, not MASKU's upstream
bus: upstream ready means spill acceptance, not descriptor consumption. The
consumers use `|mask_valid_q` without checking owner/first_element in the data
path (`vldu.sv:375`, `vstu.sv:416`). VLDU skip supplies zero data but still derives
BE from that held mask (`:417`..`:419`), not from !is_skip. Consequently a stale
mask can turn a skip into a zero write. Owner/window/lane qualification before
enqueue and ordered spill lifetime are mandatory, not diagnostic metadata.
Tail masks can legitimately have fewer than four valid lanes (`masku.sv:1210`);
do not replace the AddrGen selected-lane validity test with an all-lanes test.

The present one-element skip format is addr=0,size=vsew,len=0. Both consumers
use AXI beat geometry even for a skip. A real odd address with e16 would consume
only one byte rather than two; keep the synthetic aligned address. No zero-byte
normal terminal token exists. Last skip contributes its ordinary E bytes.
VSTU still needs source operands even for skips; no MMU/AXI transaction does
not mean no lane/mask work. Store data uses old_eew_vs1, while predicate strobes
use current vsew (`vstu.sv:430`, `:440`); keep those shuffles distinct.

## Store Response Ordering

`vstu.sv:385` bypasses WREADY and B-metadata-full for skips. `:454` suppresses
WVALID, and `:460` increments pending_b/pushes metadata only for real WLAST.
Normal store completion at `:550` requires issue finished and its pending_b=0;
the final B can be consumed and completion generated in the same cycle using
the updated count. Skip after an active write does not erase that obligation.

B metadata at `:194` holds instruction slot, original VA and element number;
all normal AW use the same AXI ID. `:530` accepts only the oldest committing
slot's B and retains its first error. The exception path also waits pending_b=0
and reports an earlier B error (`:583`). vlsu.sv:998 prioritizes that error over
AddrGen's; ara_sequencer.sv:981 captures it at store done. Default WaitForStoreB
is enabled (`ara_sequencer.sv:257`); the A/B-baseline macro disables it and must
not be mistaken for the production contract. Keep one metadata entry per real
AW/WLAST, none per skip. Delayed B and prior-write-error plus later translation
fault are real-consumer obligations. No new B-accounting blocker was found
for correctly ordered element descriptors under this default configuration.

## Normal Load Completion

Skip requires no RVALID and keeps RREADY low (`vldu.sv:350`, `:476`), but still
advances partial-word pointers. Issue bytes change once per word/end, not once
again per descriptor. All-zero-BE result entries still request all lanes and
consume commit credits. Operand requester arbitration does not suppress a
request because BE is zero (`operand_requester.sv:938`, `:955`). The normal
last result waits final grants (`vldu.sv:550`), then commit bytes reach zero
and done is emitted (`:577`). AddrGen ack cannot replace this handshake.
These normal-path facts do not waive the exception-path blockers above.

## AddrGen Candidate Diff

Reviewed parent's new diff including elen_t'(1) unit-step cast. It confines
burst splitting and delayed base alignment to vm=0; unit stride receives E,
strided retains original stride; indexed operand handshakes remain separate.
The mask lookup admits ADDRGEN/WAIT_LAST_TRANSLATION while retaining owner,
absolute element range and selected-lane validity. Skip addr remains zero,
the ordinary address advances on enqueue, and last skip wakes the frontend.
VM-disabled masked operations also wait for terminal success/fault. Active
local misalignment queues one exception marker and records VA/index/FOF;
WAIT_LAST_TRANSLATION masked faults suppress duplicate early-illegal sidebands.

No definite new structural defect found in that AddrGen diff at this review
point. This is conditional static agreement, not runtime PASS. The independent
`successor/` local TB models MMU, predicate windows, index operands and descriptor
sink; its results cannot validate VLDU/VSTU or Sv39. Parent owns real-consumer
tests and production edits. Do not change an exception oracle to accommodate
the existing consumer weaknesses.

## Identity

Consumer hashes at review (unchanged while inspecting candidate):

| File | SHA256 |
| --- | --- |
| vldu.sv | 5700da41de5b85998b3feba441a4bddda0645b4f0f00f04927baedeb0899f07c |
| vstu.sv | 139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2 |
| vlsu.sv | 9e620fb98efe420ff01ff9919461565b3c65a53bc518dc2f6cdb5f8241cf3ba2 |
| masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |
| operand_requester.sv | 327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2 |

AddrGen candidate identity is frozen separately by successor run manifests:
`470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da`.
Subsequent local successor after03 completed 32/32 PASS against that identity;
same-TB baseline comparison retained the all-off failure and identical public
event/cycle logs for five unmasked/indexed controls. See `successor/README.md`
for fixture corrections and scope. This does not close the consumer findings.
No baseline, REPAIR_CONTRACT, Aquinas report or Sv39 input was modified.
