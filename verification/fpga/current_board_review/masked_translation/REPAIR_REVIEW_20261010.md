# Independent Repair Review: Masked Nonindexed Memory

Status: design review only. No production RTL edits, RTL build, VCS execution,
or Linux launch. Extension/slide remain the integration priority. This file is
owned by the independent reviewer; the parent's `REPAIR_CONTRACT.md` was read
but not changed. Existing measurement01-04 and their reports were not changed.

## Recommendation

The proposed predicate-aware element walk is the smallest readily auditable
correctness baseline for masked nonindexed loads/stores. Keep `vm=1` on the
existing burst/strided paths; for `vm=0`, use element descriptors and existing
skip consumption. Do not first implement speculative page translation or
active-run coalescing. Those require a larger access-qualification proof.

This is conditional design agreement, NOT approval to merge an untested patch.
Reference software now passes, but the real-consumer masked-nonindexed path
does not yet exist and has not been tested. Given the extension/slide priority
and no new RTL-build authorization, finish this contract/reference checkpoint
now; implement the correctness path as a separately authorized change with
real AddrGen+VLDU/VSTU tests before integrating it. Fixing only ordinary loads
would address the measured reproducer, not close stores/strides/FOF/segments.

`REPAIR_CONTRACT.md` correctly captures the essential obligations, especially
ordered local exceptions and suppressing duplicate early-illegal notification.
The following concrete details must be part of implementation, not left to an
assumption that reusing `is_skip` or clearing `is_burst` is sufficient.

## Important Additional Constraints

1. A skip's consumer-facing `addr` must be synthetic and element-aligned,
   preferably zero exactly as the indexed skip at `addrgen.sv:924`. The real
   current VA still advances separately. `axi_pkg.sv:200,208` computes byte
   bounds from `addr` and `size`, even for skips. Counterexample: e16, real
   VA=1, skip size=1/len=0 gives lower=1, upper=1, only ONE consumed byte.
   AddrGen would subtract TWO. Eight such skips could finish address generation
   while VLDU/VSTU still require eight bytes. Use addr=0, size=encoded EEW,
   len=0 to consume exactly one full element despite a masked-off odd base.

2. Delayed alignment needs an ordered terminal marker AND one coherent
   frontend completion path in both VM modes. If using the existing
   `WAIT_LAST_TRANSLATION` as the wait state for the masked walker, enter it
   even when VM is disabled, and wake it on final active/skip success or a
   buffered local exception. Merely writing `mmu_exception_d` while the VM-off
   frontend follows its old immediate `ADDRGEN` ack path can acknowledge
   success before the registered local exception is forwarded.

3. The current `addrgen.sv:543` derives early-illegal sidebands from
   ack+cause4/6, not from whether a terminal descriptor exists. A new ordered
   alignment marker must explicitly suppress that sideband for the same
   instruction. VSTU `vstu.sv:544,578` can act on early-illegal before the FIFO
   head reaches the marker. Example: skipped prefix descriptors remain queued,
   the next active address is odd, pending_b=0; cause6 plus early-illegal can
   discard the prefix/consume the wrong head. The no-descriptor early-base
   path for unaffected operations must retain its existing notification.

These are counterexamples to incomplete candidate implementations, not newly
measured failures of a production repair. The production code is unchanged.

## Predicate Ownership and Address Geometry

Define E = SEW-in-bits / 8 = `1 << vtype.vsew`, B = NrLanes*DataWidthB,
W = B/E, remaining = `axi_addrgen_q.len` in BYTES, and
i = `pe_req_q.vl - (remaining >> vew)` in absolute ELEMENTS.
Do not confuse literal SEW=16 with encoded vsew=1 in the shift expression.

Use the VLDU or VSTU exported spill word for the current operation, not the
upstream MASKU bus. Require owner=current VID, first_element <= i <
first_element+W, and the corresponding lane-valid bit after shuffle. Resolve
the byte index `(i-first_element)*E` using current instruction EEW, as the
existing indexed helper does at `addrgen.sv:598`. Missing/wrong-owner/stale
window is WAIT, never active or inactive. Tail words do not necessarily have
all lane-valid bits set. Bits before vstart and after vl must not participate.

MASKU aligns the first window DOWN to W elements (`masku.sv:1085`), not to
vstart. VLDU/VSTU release their spill word only on a consumed VRF word or
instruction tail (`vldu.sv:455`, `vstu.sv:474`). MASKU's earlier acknowledgement
is spill acceptance, not consumption by AddrGen (`masku.sv:1235`). AddrGen
must never drive an independent mask-ready, nor wait to inspect the entire
instruction's masks before permitting the consumer to progress.

The walker may enqueue multiple descriptors for the current owned window,
then waits for the next window. No circular wait results from this alone:
already queued descriptors allow the real consumer to finish that word and
release its mask. Preserve descriptor FIFO capacity, channel ordering and
consumer operand conditions. Hold the current element/address/predicate
association throughout a pending MMU transaction; do not qualify an old
response against a newly advanced window or instruction.

Initial VA remains base+vstart*E for unit stride, base+vstart*stride for strided.
On each successful active-descriptor acceptance or skip enqueue, decrement
remaining by E and advance VA by E (unit) or the original signed stride bit
pattern (strided). Set unit slow-path `is_burst=0` AND effective stride=E;
clearing is_burst alone would reuse an ordinary request's unrelated stride.
Zero stride keeps VA fixed but still consumes each logical element. Negative
stride uses the existing width-correct two's-complement addition, not abs or
unsigned widened reinterpretation. Do not touch indexed index-spill handshakes.

For vstart>=vl/zero work, preserve the frontend no-op contract and verify that
an underflowing `(vl-vstart)` request cannot enter this walker. Never synthesize
a data-sized skip for zero elements, or wait for a mask that will not arrive.

## Skip, Counters, and Normal Completion

For a qualified inactive element, with FIFO space and preserved channel-order
conditions, enqueue exactly one descriptor:

`addr=0, size=vew, len=0, is_load=current, is_skip=1, is_exception=0`.

No MMU request, AR, AW, or dependence on AXI address READY is needed for this
skip. Do not decrement any counter while the enqueue is blocked. The final
skip must pulse the same address-generator terminal-success event as a final
active element, including `last_translation_completed` for a frontend waiting
there. Address ack is exactly once; it is not `vinsn_done`.

There is no existing zero-byte "normal terminal" descriptor. The LAST ordinary
skip/data token is the terminal progress token. For all-off e16/VL8/vstart0,
eight two-byte skips account for 16 bytes. Do not append a ninth token and do
not send `is_exception=1` for a successful all-off instruction.

| State/accounting | Required behavior |
| --- | --- |
| AddrGen remaining bytes | Minus E per accepted element descriptor; final enqueue completes address generation once. |
| VLDU byte pointers | Skip progresses exactly like E valid bytes without RVALID; RREADY stays low for the skip (`vldu.sv:350,473`). |
| VLDU issue bytes | Decrement at VRF word/end using first_payload then B, saturating; do not add a second per-skip decrement (`:439-493`). |
| VLDU result/commit | Zero-BE results still request lanes and wait for grants/final grants; commit bytes and instruction commit count change through existing logic (`:550-603`). |
| VSTU source/mask | Skip still waits for source operands and consumes them at word/end; bypass WREADY and B-metadata-full only for skip (`vstu.sv:382,414,474`). |
| VSTU bus/B | Skip has WVALID=0, no pending_b increment, no B-metadata push (`:454-466`). No phantom B credit or response is generated. |
| VSTU commit | Only after issue completion and own pending_b=0, with exception gating intact (`:550`). Prior active writes must drain B even if all remaining elements skip. |
| Instruction counters | Increment on ordinary PE acceptance; issue and commit decrement once at their existing terminal points, not at each descriptor/AddrGen ack. |

VLDU skip data is zero, but BE still comes from its OWN held mask, not from
`!is_skip` (`vldu.sv:417`). Correct owner/window/element agreement is therefore
a data-integrity requirement: a mistaken skip with BE=1 overwrites old-vd with
zero. The present no-request MMU model does not prove this consumer invariant.

VSTU keeps store-source old-EEW shuffle separate from current-EEW mask shuffle
(`vstu.sv:430-448`). Preserve both; do not use old source EEW for predicate
qualification. A skip may drive don't-care WDATA/WSTRB while WVALID=0; the
requirement is no accepted transaction, not artificially zeroing unused wires.
When earlier instructions have B responses, BREADY can legitimately assert;
the no-B property is per skipped descriptor/instruction, not a global ban.

## Active Faults and Alignment

Resolve predicate BEFORE checking the actual active VA's element alignment.
Inactive invalid/odd/noncanonical VA must not trigger translation/alignment
exceptions. On active aligned VA, retain the actual MMU request/response and
ordinary cause13/15, tval, first-fault, and retry behavior; never suppress an
active fault because some other element/window is inactive.

Local active misalignment must reserve FIFO capacity, enqueue one ordered
exception marker after the valid prefix, buffer cause4/6, tval=current VA,
exception_vstart=i, and complete the frontend exactly once. No AR/AW/MMU for
that element. Do not masquerade it as successful skip, do not retire the
consumer directly, and do not issue the no-descriptor early-illegal sideband.
The marker/prefix must remain ordered even while result grants or B stall.

FOF needs the same internal termination marker even if the dispatcher suppresses
the architectural trap and shortens VL. Existing source uses architectural
index i>0, NOT the count of previously ACTIVE elements, for non-first FOF.
An inactive prefix followed by an active fault must not reset this distinction.
VM-off local faults need the same metadata/cleanup route. Leave unaffected
unmasked/indexed exception routing and store B-error precedence unchanged.

## Segment and Scope Boundary

There is no nf in `pe_req_t` (`ara_typedef.svh:88`). Ordinary unit-segment
requests become VLSE/VSSE micro-ops, including field zero
(`segment_sequencer.sv:205-222,243`); they carry vl=vstart+1 and field stride.
Thus a generic masked-nonindexed repair includes those micro-ops: retain the
existing field-specific base, architectural vstart, and strided step. A simple
"nonindexed but not segment" local guard cannot be invented from missing nf.
Keep segment outer completion/field counters unchanged and test nonzero-vstart
and later-field fault before claiming segment coverage.

Valid whole-register/mask-memory encodings are unmasked and remain on the old
path. The decoded PE op alone does not retain lumop/nf, so do not claim this
work also audits reserved masked encodings. QBS/AKV ownership and indexed
address/data paths are outside the new walker's scope and remain regressions.

## Burst Cost and Better Alternatives

Unmasked bursts retain address, burst geometry, queue depth and completion
logic. This must be checked by transaction/cycle equivalence, not just values.
Masked strided operations already issue one element at a time; the new gating
adds predicate dependence and removes inactive transactions, not a new active
burst split there.

Masked unit-stride all-ones becomes one AR/AW per active element. For aligned
e16/VL8 on a 256-bit bus, the old single-beat transaction becomes eight narrow
transactions; stores also produce eight real B-accounting entries. Translation
request count can rise even with a hot TLB; count requests separately from page
walks. Do not claim zero stall or infer performance from a vm=1-only control.

Later coalesce ONLY contiguous, already qualified active runs bounded by the
owned predicate window, remaining elements, page boundary, AXI limits and
consumer byte geometry. Inactive-run aggregation also needs an exact byte-span
descriptor proof. No whole-instruction mask prescan, no "any active in this
word/page enables the old whole burst", and no final-WSTRB-based exception
suppression. Example: some active elements before a page boundary and all off
on the protected next page must not inherit the old burst's next-page request.

## Verification Gate Before Implementation Admission

The parent's matrix is necessary. The smallest discriminating extension after
an authorized repair is real AddrGen+VLDU/VSTU, not the old abstract sink:
all-off fault/valid controls; active page fault; final skip with VM on AND off;
odd all-off base and active odd address after skipped prefix; multiword mask
owner/backpressure; grants delayed for loads and B delayed for stores. Then
zero/negative stride, word-interior vstart, segment/FOF precise termination,
and back-to-back load/store instruction counts. Never classify silence without
actual consumer retirement/idle and a younger operation as a successful fix.

The independent Sv39 fixture/report is `SV39_REFERENCE_20261010.md`. It checks
the original scenario3 semantic core plus active retry, NOT store/stride/FOF/
segment coverage. The original Linux source/ELF pins remain intact and real
Linux signal/wait/restart acceptance stays a separate future task.

## Source Identity for This Static Review

Live source was read, not modified. Other agents may subsequently change it.

| Source | SHA256 |
| --- | --- |
| hardware/src/vlsu/addrgen.sv | a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988 |
| hardware/src/vlsu/vldu.sv | 5700da41de5b85998b3feba441a4bddda0645b4f0f00f04927baedeb0899f07c |
| hardware/src/vlsu/vstu.sv | 139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2 |
| hardware/src/masku/masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |
| hardware/src/segment_sequencer.sv | 672ddcdfafc3fb40206e9b28c9c4e5d67d40dc9fae18e577cff9c5dc586d4452 |
