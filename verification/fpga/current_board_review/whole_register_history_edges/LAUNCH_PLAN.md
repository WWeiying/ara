# Missing59 M4 Launch Plan

Preparation only. Do not launch from this document. The parent must first
strictly accept the old whole1134 partition campaign and explicitly trigger
the replacement. No old campaign progress is queried by plan preparation.

## Scope And Inputs

Use the existing, unchanged `prepared02/pair00/soc.elf` through
`prepared02/pair58/soc.elf`, one fresh SoC execution per pair, in ascending pair
order. Exact59 missing adjacencies comprise57 operation boundaries and2 seed
boundaries:118 executed calls and117 intervening original exclusions. Do not
substitute representatives, join pairs into a new ELF, rebuild, or change
original setup, target assembly, skips, or the complete1088-byte oracle.

`launch_plan01/plan.json` binds all59 exact tuples, SoC target PCs/opcodes,
original skip counts, accepted ELF/Spike identities, source pins, existing
runtime/runner helpers, the frozen539-source candidate04 image and its compiled
image files. The plan is an input/budget contract, not a reviewed runnable
worker. Its preparation script cannot launch VCS. Future minimal worker/checker
code and the parent's not-yet-issued whole1134 terminal acceptance must be
additionally bound in a new launch seal; do not edit this plan to insert them.

Image: `/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`.
Expected image.json SHA256:
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

## Admission And Slot Handoff

1. Parent supplies a pinned strict terminal acceptance for
   `whole_register_original/vcs_candidate04_01`: exact20 partitions/1134 calls,
   original366 exclusions, all actual runner and simulator return codes zero,
   complete original oracles/markers, no abort/firstfailure/cancellation/deadline,
   and unchanged source/private ELF/M4 image identities. Aggregate PASS alone
   is insufficient. Bind the acceptance and its evidence hashes before launch.
2. Confirm `ara-whole1134-candidate04-01.service` is terminal and no residual
   old-owned process remains. If its transient unit has been GC'd, require the
   pinned historical terminal evidence; missing-unit default success is not
   proof. Never terminate an old or external job to obtain capacity.
3. Transfer the old campaign's six reserved slots, rather than adding another
   six. Use one fresh read-only admission snapshot with the parent's current
   exact ownership roster. Count actual outsiders plus unoccupied reservations
   plus these six, with each process/reservation counted once; total <=24 and
   MemAvailable >=32GiB. Do not freeze stale reservations for completed owners.
   Refuse once if unavailable; no polling, automatic retry, or waiting service.
4. Only then may a parent-triggered new service start, with max6 simultaneous
   tests, no other launches and no changes to ongoing NF8 or other jobs.

## Fixed Budget

| Boundary | Limit |
| --- | ---: |
| Simulator, each independent pair |600s|
| Pair including checker and teardown |660s|
| Entire campaign work deadline |3000s|
| Service RuntimeMaxSec |3600s|
| Parallel pairs |at most6|

There are10 scheduling waves. Existing reference counts are71,875..79,947
retirements before raw exit, totaling4,422,790. At the parent-supplied planning
rate of700 retirements/s, each pair is103..115s, with a simple ten-wave estimate
of1143s plus simulator startup, trace checking and contention. This is a
planning estimate, not measured pair DUT performance. Spike's extra5000 HTIF
exit-batch instructions per ELF are not counted as useful pair work.

The59 individual600s worst cases do NOT fit within3600s. The campaign deadline
is deliberately independent: at3000s, cancel outstanding/queued work, retain
evidence and report NOT_ACCEPTED. Do not silently increase budgets or retry.
The remaining600s service margin is for bounded cleanup/evidence extraction,
not new dispatch. Any deadline at any stage vetoes aggregate PASS.

## Minimal Execution And Acceptance

Reuse sealed integration runtime/build outputs and `integration/run.py` runner
semantics; do not rewrite the framework. A small owned adapter must add the
pair-specific CSV checks below rather than treating console PASS as sufficient.
No simulator/ELF build is needed. No new broad test suite is requested.

- Validate all59 coverage and all reference pins before dispatch. Each pair
  must run its exact private copied ELF on the pinned M4 simulator, with seed1,
  complete commit CSV, no FSDB, and no substituted instruction/setup.
- From actual CSV, enforce complete contiguous retirement, no trap/default
  handler/mismatch, exact two original call entries and arguments, two target
  PCs/opcodes in predecessor-successor order, four whole preloads and two
  output whole stores. Use SoC symbols/targets, not Spike PC equality.
- Check both complete1024-byte input initializations and1088-byte old-output
  initializations, both ordered1088-byte actual output reads with original
  expected values, guards, returned vstart and captured starting vstart. Total
  output-byte checks must be128384. Preserve the existing permitted original
  skip rules; do not treat skipped tuples as executed coverage.
- Reconstruct inherited vtype from retired vset instructions and known input
  register values where available. In particular preserve pair15/35/55's
  op15 -> op16 inherited VILL; expected second-entry vtypes are pinned per pair.
  Do not add instrumentation or reset vector state between calls.
- Require exact `RVV_WHOLE_PASS cases=2 skips=N errors=0` with each pair's
  original N, its exact BOARD_CASE_PASS marker, BOARD_REPLAY_PASS, raw exit0,
  CTRL/tohost0 and simulator finish. Reject every failure marker even when
  PASS text also exists. Require actual runner/simulator rc0.
- Stop new dispatch on first failure, exception, signal, timeout or pin drift;
  cancel owned outstanding work and preserve all artifacts. A single monotonic
  deadline/abort state must also cover checker completion. Publish terminal
  PASS only after no pending cancellation, every pair accepted, all59 membership
  exact, no firstfailure artifacts/abort reason, and pre/post pins unchanged.
  Never let a late timer or signal coexist with an accepted terminal PASS.
- A subsequent independent terminal audit must confirm service success and
  reconcile all59 results/CSV oracles/elapsed bounds. No retry or resume can be
  hidden inside a complete59 acceptance.

Proposed service name: `ara-whole-history59-candidate04-01.service`, direct
worker ownership, `RuntimeMaxSec=3600`, `KillMode=control-group`, `Restart=no`,
stdout/stderr append to a new local service.log. No launch command is provided
until the minimal adapter/checker and terminal handoff seal are reviewed.
After authorized startup, confirm actual simv and one short trace-growth window,
then stop polling. Retain all old partition and failed-preparation evidence.

## Claim Boundary

Even all59 PASS would accept only local missing adjacency boundaries under
fresh-start context on M4. It would not establish full1134 continuous history,
original Linux ELF/OS replay, arbitrary deeper queue/layout history, or behavior
of the original excluded tuples. Current preparation is not DUT PASS.
