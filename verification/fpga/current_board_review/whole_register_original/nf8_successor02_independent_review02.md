# NF8 Successor02 Independent Review 02

Status: CODE_REVIEW_NO_BLOCKER_PENDING_TERMINAL_HOST_AND_READY_PLAN.
No new blocking code finding in the exact successor below. This is not final
launch clearance: do not set independent_review.no_blocker=true from this note
until the host48 terminal evidence and sealed ready plan receive final review.
No DUT launch, simulator replay, production/source edit or legacy-job polling.

Reviewed 2026-10-11. Relative code root:
`../masked_translation/nf8_strided_review/sv39_full192/`.
Hashes checked both before and after review:

```text
vcs_jobs8_successor02.py 77417da7b60042fbf36f1b43287d444377ea5bcc7a59101eb5b9e44ca18a1061
test_successor02.py 835f1075a764b39b3d1f0e80e19632bc4ada69f5c0dfc779999dca15683a0046
SUCCESSOR02_REVIEW.md 404aaf049c6b4caa9786283eebeedfd254520d476a0540b1407353b89f256b8b
```

## Findings Closed

- Prior timeout/aggregate false-PASS reproduction is addressed. GroupTerminal
  serializes deadline/abort inspection and acceptance; elapsed monotonic time
  independently vetoes a delayed timer callback. Timeout state is persistent.
  Accepted terminal callbacks are stale; timer cancel is followed by join.
- Expensive checker.finish(), input/ELF checks and post-campaign pin/image
  verification execute outside the shared abort lock. Independent additional
  test blocked finish() on an event while a real separate timer thread fired:
  timeout was observed before finish returned; returned and persisted status
  were FAIL, timed_out=true, and firstfailure existed. No simulator was spawned.
- Exclusive-create rewriting is fixed with successor-owned same-directory
  temporary JSON, flush/fsync and os.replace. Tests use actual filesystem
  replacement for existing plan/template and for PASS revocation. The original
  support.save exclusive-create contract and sealed inputs are unchanged.
- Campaign acceptance requires exactly48 groups, all PASS, no timeout/abort,
  unchanged identities. SIGTERM/SIGINT are masked across final publication;
  pending cancellation is checked before/after publication and revokes PASS.
  CampaignAbort's terminal edge makes subsequent signals post-completion.
  This edge is the documented acceptance boundary, not process termination.
- REVIEW resolves to the existing original independent report via parents[2].

## Verification And Limits

- Independent rerun: all14 successor host tests PASS, including real self-
  SIGTERM during publication and real filesystem replacement. Temporary test
  directories were redirected into this reviewer's whole_register_original
  directory and automatically removed; scripts and prepared inputs untouched.
- Extra separate-thread blocked-finish test PASS as described above. Existing9
  scheduler/capacity tests were independently passed in review01. This does not
  replace their required ready-plan test log or full48 host CSV/ledger checks.
- Atomic publication still performs file I/O/fsync under the shared lock. This
  can delay peer callbacks under filesystem stalls; it is not a hard-real-time
  guarantee. Expired acceptance is still rejected by monotonic time, and the
  externally enforced18000s cgroup limit remains necessary. No expensive full
  oracle/trace scan is covered by that lock in the reviewed code.
- A live complete.json alone is never final acceptance. Require successful
  terminal service status, consistent no-abort/firstfailure evidence, exact
  accepted group membership and unchanged identities. Interrupted publication
  or nonzero service termination must not be promoted to PASS.

## Outstanding Launch Gates

At review end, dut_host_all192_01/status.json and a vcs_jobs8 ready plan were
absent. Submit those terminal artifacts for final independent pin/membership/
ledger review; no polling or launch is performed by this reviewer.
The original vcs_jobs8.py worker remains known-bad and must not execute.

Any eventual clearance must bind this successor and test SHA, complete host48
evidence and ready-plan SHA; all192 trials in48 fixed groups; pilot0 first;
max8;2400s simulator/2520s group/18000s service bounds; frozen candidate04;
NF7/parent38/gather/whole reservations2/4/4/6 plus own8; and gather unit
ara-gather75-candidate04-01.service. Unit ara-nf8-full192-candidate04-01.service
must directly own the worker, use control-group cleanup, Restart=no and local
append stdout/stderr. Source-derived Sv39 scope, not Linux/SIG/root-cause closure.

The reviewed pins and outcome are sent to parent via the available task-message
interface for relay to Aquinas; no direct send_input API is available here.
