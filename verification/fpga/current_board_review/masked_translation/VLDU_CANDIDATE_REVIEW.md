# VLDU Candidate Static Review

2026-10-10. Final reviewed VLDU SHA256:
`4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab`.
Read-only review; no RTL edit, build or new simulation. Tesla owns dynamic A/B.
The earlier unconditional-ready-gate SHA `19fd5b69...` is superseded below.

## Remaining Integration Findings

### 1. Blocker: Refused Younger Load Can Still Complete AddrGen

The final ready expression fixes empty-issue-queue arrival, but still refuses
new requests while a faulting owner is present or its exception FSM is busy
(`hardware/src/vlsu/vldu.sv:339`, acceptance at `:702`). That refusal is not
coordinated with the other consumer of the same request:

- `ara.sv:357` broadcasts without testing LoadUnit ready.
- `vlsu.sv:567` sends the same normal_pe_req_valid to AddrGen and VLDU; it does
  not qualify AddrGen acceptance by VLDU acceptance.
- `addrgen.sv:309` accepts a new load in IDLE without a VLDU-ready input.
- `ara_sequencer.sv:1013` withdraws a load request after AddrGen ack and
  operand/MASKU acceptance, with no tracked VLDU acceptance. Its per-FU queue
  credits (`:1312`) enforce capacity, not the new exception-ready condition.

Concrete static witness: unmasked non-first FOF load A faults with prefix
writeback still delayed. AddrGen acknowledges A before those writes finish.
Dispatcher `:4368` shortens VL and suppresses the trap, but enters WAIT_IDLE_FLUSH
only for masked FOF. A disjoint unmasked load B can therefore be broadcast while
A is in VLDU WAIT_RESULT_QUEUE. AddrGen accepts B; VLDU refuses it. With room in
the descriptor FIFO, AddrGen can issue and acknowledge B while A still waits
for final grants; the main sequencer can withdraw B's valid. B then has no VLDU
instruction record to retire. Choosing delayed final grants makes this window
independent of frontend latency. B can itself be a first-element fault, leaving
its exception marker with no accepted owner after A drains.

This is a static counterexample to the combined protocol, not a new measured
failure of final SHA. The new `!vinsn_issue_valid` alternative cannot help when
A remains the issue owner. Masked fault/FOF's dispatcher flush barrier normally
prevents this witness; it does not establish safety for unmasked FOF.

Required contract before integrated signoff: do not let a load's broadcast be
released based on AddrGen ack unless its VLDU context was actually accepted;
and make fault cleanup's instruction-serialization assumption true. A scoped
fault/FOF completion barrier is one possible design direction. Blindly ANDing
all existing broadcast valid with VLDU-ready is not approved here: retained
owner/operand handshakes must still be able to complete. Parent owns the design.

### 2. Existing Constraint: Queued Younger Context Can Prevent Fault Entry

`vldu.sv:617` requires commit_cnt==1 before entering the exception FSM, counting
ALL accepted instructions, not just older instructions. If unmasked load B is
accepted after A's AddrGen fault ack but before A's exception marker reaches
the descriptor head, commit_cnt includes A and B. Once the marker reaches head,
A cannot finish without exception handling, B cannot consume its later tokens,
and commit_cnt cannot reach1. The new gate observes the marker at the head, too
late to exclude that earlier acceptance. A delayed prefix R beat can create
this alternative window; final-grant delay creates finding1's window instead.

This entry condition predates the patch. It is not evidence against partial
FIFO insertion itself, but it means isolated-owner unit PASS is not proof of
multi-instruction fault/FOF safety. Both findings concern the same missing
fault-epoch/acceptance contract, not two unrelated requested RTL changes.

## Final Arrival Expression

Current `vldu.sv:339` is:

```systemverilog
pe_req_ready_o = !vinsn_queue_full && ldu_ex_state_q == IDLE &&
                (!vinsn_issue_valid ||
                 (!early_illegal_pending_d &&
                  !(axi_addrgen_req_valid_i && axi_addrgen_req_i.is_load &&
                    axi_addrgen_req_i.is_exception)));
```

With no issue owner, descriptor-first, same-cycle descriptor, early-sideband-
first and same-cycle sideband all leave ready asserted (provided not full and
exception FSM IDLE). The owner is accepted at the edge; the exception FSM sees
registered issue-valid next cycle. A sideband pulse is retained by
early_illegal_pending. This statically fixes the old unconditional gate.
An older instruction waiting only for commit does not invalidate this reasoning:
if issue_cnt is zero, the new faulting owner can still be accepted; older normal
commits can subsequently reduce commit_cnt to1.

Read evidence, not rerun:

| Existing artifact | Pinned VLDU | What it establishes |
| --- | --- | --- |
| consumers/arrival_candidate04 | 19fd5b69a25fb677250d1d00878279ff68f016b0520e787afacd8581582ac4f0 | Four old-gate cases: accepts0/pops0/dones0 despite held PE-valid. |
| consumers/arrival_baseline05 | 5700da41de5b85998b3feba441a4bddda0645b4f0f00f04927baedeb0899f07c | Four baseline cases accept once and finish once, but retain issue_bytes16/idle0. |

Neither artifact is dynamic validation of final SHA `4e46a473...`. Their
PROBES_COMPLETE label describes observation collection, not architectural PASS.
Parent's baseline partial-done15/write35 observation remains the motivating
writeback-order evidence; it was not recreated by this review.

## FIFO and Final Grants

The partial-prefix change is coherent locally under the ordered single-owner
exception contract:

- VALID_RESULT_QUEUE (`:624`) inserts only when partial byte count is nonzero,
  marks all lanes valid, increments occupancy and advances the write pointer
  once, then leaves that state. First-element faults enqueue no phantom word.
- Normal result pop updates the same `_d` occupancy before partial insertion.
  With one occupied entry in the depth-two FIFO, read/write slots differ, so
  simultaneous pop and partial push neither overwrite each other nor lose a
  count update. With zero entries the normal pop is disabled. With a full queue
  the old-q full check postpones push even if a pop happens that cycle: a
  conservative exception-path bubble, not overwrite or underflow.
- The terminal descriptor excludes the normal R/skip ingestion path. The
  early-illegal path waits for no descriptor before starting cleanup. Thus
  ordinary enqueue and partial enqueue do not compete under this contract.
- WAIT_RESULT_QUEUE (`:639`) now requires updated occupancy0, all valid bits0
  and all final-grant bits1. Occupancy may retire early on nonfinal words, but
  this extra gate still waits for outstanding lane writes before exception done.
- Actual `operand_requester.sv:117` uses a one-entry `stream_register`, whose
  ready is downstream-ready OR empty. Each lane has at most one outstanding
  load write there. `vldu.sv:535` ORs a final grant, then `:543` clears the bit
  if a new result is accepted in the same cycle. Clear priority correctly means
  an old write completed but a new one remains outstanding. The new item cannot
  have a same-cycle final grant through this nontransparent register.
- Resetting final-grant bits to1 represents no outstanding writes, allowing a
  no-prefix first fault to finish. It cannot bypass a real initial result:
  pending result-valid prevents retirement until acceptance, which clears bits.

No additional FIFO pop/push or final-grant attribution defect was found in the
new local logic under those conditions. This is not a claim about arbitrary
mock grant protocols or unaccepted/misowned instruction contexts.

## Completion, FOF and Normal Cycles

HANDLE_EXCEPTION (`:647`) clears issue/commit bytes and partial-word pointers,
resets sequence/first-payload state, and clears the empty write slot only after
drain. It releases an owned buffered mask. Normal done is gated to IDLE (`:583`),
so partial-entry accounting reaching zero while WAIT_RESULT_QUEUE cannot also
retire the same instruction normally. HANDLE_EXCEPTION emits one done and
decrements counts once; ready remains false in that state. On the following
cycle, an isolated owner's commit count is zero, preventing duplicate done.
Do not infer this protects the invalid cross-instruction situations above.

First fault, partial prefix, whole-word prefix and zero-BE skipped prefix all
take appropriate distinct paths. FOF still carries an internal exception marker:
architectural suppression/VL change belongs to the dispatcher, not VLDU. No
consumer bypass is justified because a FOF exception does not trap.

For an exception-free instruction stream the new ready terms reduce to the
old !full, and the done guard is true. Existing data ingestion, output geometry,
normal count updates and writeback pacing are unchanged. Reset final-grant1
cannot advance normal completion before a real request is accepted and its
final grant arrives. Therefore no normal-cycle change is predicted statically;
exact-cycle equivalence must come from Tesla's same-TB A/B, not this review.

## Review Boundary

Approval is limited to the local partial-FIFO/final-grant/cleanup direction and
the repaired empty-owner arrival expression. Integrated signoff still needs the
load-acceptance/fault-epoch boundary resolved or a proven upstream exclusion.
No production files, consumer tests, frozen evidence or AddrGen successor inputs
were modified. No additional cases were built or run.

Other current identities used in the protocol trace: ara_sequencer
`f1d6095e1ade018b9225678a493438da04e7d84f68a956bdf7a116941bfafc5b`;
ara_dispatcher `8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2`;
ara.sv `1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da`;
vlsu.sv `9e620fb98efe420ff01ff9919461565b3c65a53bc518dc2f6cdb5f8241cf3ba2`.

## Fault-Only Load Completion Barrier Review

Static approval of the proposed sequencer contract, not signoff of an
implemented patch or new simulation. The reviewed scheme retains a matching
LoadUnit completion through WAIT and delays a faulting load's final response
until that completion. It closes the younger-load admission window described
above without delaying normal, nonfaulting loads. Required details:

- Preserve request withdrawal. In particular, a no-source load can withdraw
  `pe_req_valid` on AddrGen acknowledgement as before. Completion retention
  must not require request-valid to remain high; WAIT retains the request ID.
  The barrier gates the final dispatcher response, not the operand request.
- Latch only `pe_resp_i[NrLanes+OffsetLoad].vinsn_done[pe_req_o.id]` for the
  current load. Other VIDs and other functional units cannot release it.
  Clear at actual new request allocation, not repeatedly while input valid is
  held. Capture completion throughout WAIT, including before AddrGen ack.
- Update exception and completion next-state values before evaluating the
  final gate. Use `addrgen_exception_d.valid` and
  `memory_load_completed_d`, so an exception arriving with ack cannot escape,
  while a matching done arriving with ack need not incur another cycle.
- Append the logical condition `!is_load(pe_req_o.op) ||
  !addrgen_exception_d.valid || memory_load_completed_d` to the existing final
  response prerequisites. Do not bypass operand/MASKU acceptance or change
  the existing store/B-response rule. The store A/B baseline build option
  must not accidentally disable the load barrier.
- FOF must use the internal AddrGen exception before dispatcher suppression.
  An architecturally suppressed fault still requires prefix drain and cleanup;
  the FOF response/VL update cannot admit younger work before matching done.
  A successful FOF without an internal fault retains the normal ack-only path.
- Older queued loads may drain while the barrier is held. Excluding younger
  allocation lets the fault owner reach VLDU's `commit_cnt == 1` condition.
  VLDU cleanup and done do not await the dispatcher response/flush, so this
  ordering introduces no identified circular dependency.

Scope and remaining boundaries: `is_load()` also includes QBS/AKV clients.
Terminal ack+done in one cycle is covered by updated-state evaluation; normal
nonfault early-ack behavior remains unchanged. This is not protection against
a new fault reported only after an already released early acknowledgement.
No new claim is made about those clients' delayed-error contracts. The earlier
readiness and completion findings are closed only when the sequencer exclusion
is implemented with these identity, withdrawal, and FOF conditions and verified
by its owner. No RTL or simulations were changed for this review.

### Implemented Barrier Static Check

Read the actual sequencer diff at SHA256
`58d8e431cc222f0584b6a13086720adcd53b72daf6f57d4f024b39844e3f98e8`.
The new code satisfies the above gating contract: allocation/response/reset
clear the latch; WAIT updates only matching LoadUnit/VID completion without a
request-valid requirement; the final guard uses updated exception and done;
withdrawal and store conditions are unchanged. The store baseline macro does
not bypass this guard. No new blocking defect was identified in that diff.
FOF is qualified using the internal fault, not the later architectural trap.
The existing slide mask-RAW hunk in the full git diff is unrelated, not a new
barrier change. Dynamic A/B remains Tesla's responsibility; none was run here.
