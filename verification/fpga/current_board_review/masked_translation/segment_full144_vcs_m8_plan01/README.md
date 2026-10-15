# Full144 M8 Worker Preparation

Prepare/dryrun only. No DUT, reference rerun, compile, RTL edit or image build.
`replay.py` reuses the frozen image context, runner dryrun, monitored process,
resource admission and atomic abort-aware publisher. A single case-specific
RVFI observer is in `checker.py`; original source/ELFs remain sealed.

## Scope And Exit Protocol

Exactly the complete original e16/m2 alignment144 configurations in original
order, eight byte-identical helpers, capacity128. Each call resets four8192B
buffers and128B predicate. Sv39 is real; Linux clone/COW/signal/context and the
historical Linux page fault are not reproduced or claimed accepted.

The reference measured120 numerical +24 capability cases is evidence, not a
DUT prediction. Any eligible call may complete numerically. All144 numerical
is valid. Capability requires actual target PC, direction-correct cause4/6,
phase1, offset1, VL>0, active predicate and actual VL/type context. Staging,
readback, page faults, phase-store faults and all-off/VL0 traps fail. No
numerical readback or return CSR is invented for a trapped child.

Frozen M8 `ara_tb.sv` lines1532-1558 prints the ordinary nonzero-source warning
and calls `$finish(exit >> 1)`; it does not `$fatal` for source77. The worker
does not use an ordinary runner's SUCCESS-only decision. It recognizes only
the exact `Core Test *** FAILED *** (tohost = 77)` warning, provisionally during
monitoring and finally only after full144 RVFI evidence proves source77.
All other FAIL/Fatal/Error markers veto, including UnexpectedFatal. Partial
terminal-warning text is deferred until distinguishable; a partial source
failure marker terminates immediately. Source marker and `$finish` are required.

`source_exit` and actual numeric process returncode are separately retained.
Numerical completion requires source0 and simrc0. Capability requires source77
and a declared simulator return of0 or77, never arbitrary nonzero success;
`$finish`'s argument is not assumed to be a Unix exit status. Neither is
rewritten. Timeout, abort, raw failure, missing complete oracle or any other
numeric process exit remains NOT_PASS. A future unexpected protocol variation
must be preserved and reviewed offline, not automatically retried or excused.

## Actual Trace Evidence

Every retire PC/encoding is checked against the unchanged SoC ELF. Scalar
memory accesses require actual RVFI effective address, shifted byte enable,
source/destination register value and signed-load behavior. Before every
helper all four buffers and mask are checked both for complete actual reset
stores and their full contents. Original contiguous helper PCs, eight args,
VL/type/start and phase are checked. Handler CSR readback is bound to stored
context; post-helper CSR reads and terminal restoration are checked.

RVFI does not supply vector write payload. The observer invalidates only
vector-written storage and requires subsequent actual scalar loads to recover
every numerical result byte, independently compared with the original oracle.
It never writes expected vector results into its memory model. Each numerical
case requires all1024 actual and1024 expected scalar word reads, including
guards/tails; initialization alone cannot pass the oracle.

CVX request/response owners and target exceptions, architecture order and
backend VID allocations/completions are checked. The frozen generic validator
additionally checks retired/CVX/architecture sequences and permitted harmless
CSR transport replay. Both parse the same closed CSV once each with matching
row/retire/cycle totals. Store architectural visibility is checked; no claim
of direct AXI B measurement or zero internal MMU activity is made.

Per-owner completeness is additional to aggregate alloc/done equality:
architecture memory owners must match actual memory requests; every staging,
readback and mask-load owner must complete at least one uop. Successful targets
with VL>0 require a completed owner even when all mask bits are off. VL0 targets
and actual target exceptions may elide a backend allocation, without predicting
a count. All original non-config helper offloads are memory instructions;
the decoded helper set has no additional arithmetic offload class.

This all-off distinction follows frozen M8 RTL: `ara_dispatcher.sv:5968`
elides empty architectural intervals, not predicate contents;
`segment_sequencer.sv:203` starts the field sequence on request transfer and
`segment_sequencer.sv:232` continues field requests;
`vlsu/addrgen.sv:922` handles an inactive predicate after backend acceptance
by enqueueing skip descriptors. Host negatives remove an entire required
owner alloc/done pair, including the VL>0 all-off case; generic equality alone
would not detect that deletion.

## Admission And Budget

M8 image is explicitly `/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image`.
Source87 evidence pins, reference raw/result/checker, immutable SoC ELF,
image/config/snapshot, imported local code, worker and Host are bound at
prepare and verified again before/after execution. Runtime ID is separate
from historical source name. Private ELF, exact seed/preload/cwd and image
provenance are checked. Actual monitored child outcome is fsync-persisted
before any post-check can throw. Audit subprocess waitcode is separately saved.

One job, simulation10800s, worker+observer12000s, direct service13200s,
no retry/FSDB/build or automatic extension. Source cost/proxy estimates remain
qualified: about135-150min including20% margin at closer observed rates;
slower273/s is over3h. Timeout alone is not an RTL-bug finding. No scope or
oracle is removed to meet the budget. Resource admission at authorized run
requires total simulator cap24 and available memory32GiB; prepare does not
query live simulations.

`prepared01/ready.json` supplies the exact future service command. Launch is
fail-closed until an independently pinned entry review explicitly accepts
the source/reference evidence and worker, and a separate parent authorization
binds the exact plan SHA/unit/budget. Preparing this plan is not that approval.

Independent review JSON required fields:
`decision=ACCEPT_SEGMENT144_M8_WORKER_ENTRY`, `plan_sha256`,
`reference_ready_sha256`, `blocking_findings=[]`,
`reference_raw_review_accepted=true`, `worker_review_accepted=true`,
`evidence_pins` (actual paths/hashes). Raw-review acceptance means reviewing
the recorded reference and its checker; it does not claim a second independent
full raw parse when one was not performed.

The actual source/reference review is already pinned separately:
`../segment_full144_review_zeno01/REVIEW.json`, SHA
`e4231d1b5084b0751d451d1866c9694dcead70b8136487f068e3d48259f0b5bf`.
It accepts source/reference scope only, not this worker or a DUT launch.

Parent authorization fields: `decision=AUTHORIZE_SEGMENT144_M8_ONCE`,
`plan_sha256`, `entry_review_sha256`, `unit`, `budget_risk_accepted=true`.
No approval file or review result is fabricated by this preparation.

## Host

`host02.json` records the latest synthetic RVFI boundary tests using actual SoC PC/code,
all144 full resets and numerical oracles, eligibility and target/cause/phase
negatives, actual addr/BE/value/result/last-guard checks, owner failures,
exit separation and durable-outcome/late-abort tests. The real subprocess
monitor test runs a tiny Host Python emitter, never simv. These are checker
tests, not hardware evidence. Earlier preparation/Host failures remain in
`host_attempt*.log` and actual wait records rather than being overwritten.
