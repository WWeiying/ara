# Physical Operand and Maintenance Finding

This is the latest offline result. Original `first_error.json`, README, and
WAVE_ADDENDUM remain unchanged as earlier analysis stages. No simulation,
production edit, timeout change, or sealed-file modification was made.

## Measured Boundary

The last backend allocation is CSV cycle367644 / time367659.5ns. It is VLXE,
vs2=vd=4, request vstart=15, eew_vs2=3 (EW64), old_eew_vs2=2 (EW32),
source_snapshot_replay_vs2=0, snapshot-valid=0. AddrGen holds the same descriptor
from 367660.5ns. The later **exception CSR** vstart=16 is not a new request
starting at16.

Clock phase matters: recorded stable pre-rising-edge monitor cycle C corresponds
here to time C+15.5ns. A post-edge value appearing at time T is sampled by the
consumer at the next rising edge T+1ns, if it remains valid. The event records
use both units explicitly, without equating CSV cycle numbers with absolute ns.

| Event | Time ns | CSV monitor cycle | Measured values |
| --- | ---: | ---: | --- |
| All four lane q8 operand requests handshake | 367661.5 | 367646 | vs4, eew2, vstart6, vl16, replay0 |
| All four requester bank3 grants | 367662.5 | 367647 | requester address19, vew2 |
| First word queue push; all four bank4 grants | 367663.5 | 367648 | requester address20; previous word enters queue |
| Second word queue push | 367664.5 | 367649 | all four queue inputs valid; replay0 |
| Bad address first sampled with mmu_req_o=1 | 367679.5 | 367664 | mmu_vaddr_o=0x0000400040017000 |
| CVX exception response/ack | 367696.5 | 367681 | later handler reads vstart16 and the same bad mtval |

Queue input data is available one cycle before the queue-push edge above.
It equals `vrf_operand[8]` on all lanes. The two consecutive aggregate words are:

| Lane | First word (element12..15 range) | Second word (element16..19 range) |
| ---: | --- | --- |
| 0 | 0x0001d00000003000 | 0x0000000000017000 |
| 1 | 0x0000000000000000 | 0x0000000000004000 |
| 2 | 0x0000a00000010000 | 0x0000000000011000 |
| 3 | 0x0000000000000000 | 0x000000000001e000 |

The first word is the **EW32 physical layout** of four logical 64-bit indices
`3000,10000,1d000,a000`. The second is the **EW64 physical layout** of indices
`17000,4000,11000,1e000`. Dispatcher records v4=EW32 and v5=EW64 throughout.
Applying the frozen four-lane EW32 byte-shuffle table to the second actual word
produces first index `0x0000400000017000`; adding base0x40000000 gives the exact
bad address observed upstream of the MMU and in the handler. This is no longer
an inference solely from the final numerical coincidence: the actual upstream
word and its preceding differently laid-out word are recorded.

The retained profile does not contain AddrGen input/dequeue, deshuffled_word,
or word_lane_ptr. Thus the **queue entry and MMU request are measured**; the
intervening byte transformation is evaluated from frozen RTL, not falsely
claimed as a direct observation of those missing ports. FIFO push is driven
by operand_valid_i (`operand_queue.sv:105`); this is the actual valid input,
not stale data while valid=0. Internal FIFO full/flush are not directly dumped.

## Snapshot and Maintenance

`handshakes.json` matches every one of the 20 CSV uop_alloc cycles to the
sequencer request present on that edge: one VLE, two initial VSLIDEDOWN helpers,
and 17 VLXE allocations. The two helpers are initial capture and destination
layout maintenance. There are **no further maintenance allocations on any
retry**, even though the mixed v4/v5 layout persists. CSV insn alone cannot
distinguish these helpers, since it retains the original instruction bits.

The initial snapshot-valid bit rises at357443.5ns and clears at357462.5ns.
Only the first VLXE descriptor uses snapshot replay. Every subsequent VLXE
uses old_eew_vs2=EW32 and replay0. The last request's queue inputs are also
independently measured with lane replay-valid0. Correct initial capture does
not mean late retries are still served from that snapshot.

Static frozen dispatcher order agrees with the parent's dedup hypothesis:
mixed indexed source requires normalization; the overlapping-source precedence
at5415 suppresses destination reshuffle while source reshuffle is needed;
`indexed_load_index_overlap` is then false; the same-register dedup at5650
has no indexed-overlap exception and can clear the remaining source request.
Observed direct VLXE issue without normalization/capture is consistent with
that path. `reshuffle_req` itself is absent from the capture, so the Boolean
sequence is a static reconstruction, not a directly measured signal trace.

Changing the single old-EEW tag to EW64 for this whole request is not by itself
a coherent repair: that would misinterpret the preceding EW32 word. The
observed mechanism is **mixed physical layout entering one request-wide
interpretation, with the initial snapshot no longer selected and no retry
normalization**. RTL repair selection and validation remain separate work.

Evidence: `operand_probe.json` (post-delta events and metadata transitions),
`handshakes.json` (pre-edge grants/pushes, all allocations, actual MMU requests),
and `operand_finding.json` (checked word transform and evidence hashes).
