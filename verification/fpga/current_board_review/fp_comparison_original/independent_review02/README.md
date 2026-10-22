# Independent review 02 — FP2 successor06

**BLOCKER / NOT CLEARED:** one P1 signal-publication boundary finding remains.
The old CSV cancellation bug and the review01 missing dependency pin are fixed
in the inspected code. This report grants no launch authority.

Plan06 SHA256:
`396cca255723e58fb5ba089220ed94edbb09c5a9417a69ac81e044de0d54d1af`.
This equals `preflight.json` and the parent's supplied hash. All **2,737 pins**
matched independently before and after host review. Sealed05 still hashes to
`f0edb7011fdd4a69e0b633f03fa94405c072b7874367b69e3ab864e570069667`.

Only `independent_review02/` and isolated temporary host directories were
written. No producer prepare/work entry point, DUT, build, service launch,
active-job polling, shared edit, plan05 edit or plan06 edit was performed.
The supplied host suite's frozen-runner fixtures override prepare/build/DUT
execution with temporary host fixtures; they do not prepare or build a DUT.

## P1 — pending signal can precede the documented decision and still publish PASS

Location: `../replay_restart_abort.py:78–88`, especially `:82–85`.
Claimed boundary: `../candidate04_restart_plan06/README.md:52–55` says the final
eligibility/no-abort decision is the terminal linearization boundary.

`publish()` blocks SIGINT/SIGTERM, samples `sigpending()` at line82, then
separately computes `passed = eligible and not self.is_set()` at line84.
A signal generated after the pending-set sample but **before line84 executes**
is pending in the kernel; its handler cannot update `signal_seen` while blocked.
Line84 therefore selects PASS, line85 publishes it, and line88 delivers the
signal too late. `publish()` returns True with the abort latch now set.
`work():293` consequently maps this successful return to exit0 without another
veto. Atomic file replacement prevents partial JSON; it does not make the
pending-signal sample and terminal decision atomic.

Independent reproduction uses a Python line trace only to schedule **real
`os.kill(os.getpid(), SIGINT/SIGTERM)` immediately before line84**. No abort,
publish, `sigpending`, `os.replace`, or JSON-writing function is mocked. The
real rename writes a real temporary terminal file. Both signal variants show:

| Observation | SIGINT | SIGTERM |
| --- | --- | --- |
| Signal pending before decision/rename | true | true |
| Terminal file already existed at signal generation | false | false |
| `publish()` return | true | true |
| Abort latch on return | true | true |
| Published status | PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4 | PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4 |
| Published `aborted` | false | false |

The hook widens a real scheduling window deterministically; it does not alter
production decision logic. Evidence is in [evidence.json](evidence.json),
`race_reproductions` entries with `before_line: 84`. The additional line85
experiments also publish PASS, but occur **after** the documented decision;
those are boundary characterization, not a separate defect under that definition.

The 26 new tests do not cover this interval: `test_pending_signal_veto`
(`../test_restart_abort.py:233–240`) queues its signal before entering publish,
and serialization cancellation (`:211–222`) occurs before the pending sample.
They correctly pass while this later window remains.

Resolution needs an explicit consistent cancellation/terminal ordering
contract and implementation/test evidence for its exact boundary. If the
intended rule instead treats the earlier pending-signal snapshot or start of
the masked commit region as the boundary, that is a materially different
contract for the parent to review; the current README names the decision.
This reviewer has not changed code, weakened the requirement, or cleared the
launch on that alternative interpretation.

## Checks that passed

- **Actual CSV cancellation:** independently reran the supplied real frozen
  executor/report/CSV fixture. The old checker returns PASS/rc0 with
  `run.status=INTERRUPTED`; the successor returns CANCELLED with INTERRUPTED.
  `AbortLatch.accept()` at `:64–68` corrects late row status, and
  `terminal_inputs():192–204` requires COMPLETE, PASS:2, exact two names in both
  returned rows and summary, rc0 and matching artifact paths. An INTERRUPTED
  run with PASS rows is rejected.
- **Sticky abort and expensive checks:** the latch cannot clear; admission,
  raw/CSV failures and exceptions set it. CSV reads, pin hashing, identity
  validation and serialization of both terminal alternatives occur outside
  its lock. Outer signal handlers span post-run validation and publication;
  the frozen runner restores them after its temporary handlers. Cancellation
  before the pending sample prevents terminal acceptance.
- **Dependency closure:** `integration/prepare.py` now has the expected
  `c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8` pin.
  `verify():122–129` independently hashes bytes instead of trusting this helper
  to verify itself. Loaded production project modules, including the frozen
  runner, match plan pins; the review harness itself is excluded from this
  production-closure comparison. `module_gate` runs before launch and after
  execution. Review01 F1 is closed for this snapshot.
- **Process accounting:** `process_is_simv():94–96` recognizes comm **or** argv0
  basename; `scan_simv():99–113` records matched processes and passes them into
  the inherited cgroup/reservation accounting. The changed-comm/five-unknown-
  processes negative is correctly rejected. Parent-supplied unit truth and
  coordinated global quotas remain operational assumptions.
- **Scope and budget:** both case entries and the held682 entry equal sealed05
  exactly. Execution remains two 130-call ELFs, jobs2, per-case3600s, no build,
  original full scalar/flags oracle and full CSV checks. Held682 cannot enter
  the executable list. The template supplies prefix5 unit
  `ara-arithmetic-prefix5-candidate04-01.service`. The README requires a direct
  FP service with outer4500, stop grace120 and KillMode=control-group.
- **Authorization:** explicit authorize flag, approved plan SHA, pinned parent
  review, inherited terminal/admission gates and fresh one-shot output remain.
  Post-run image/pins/module/approval/evidence checks precede terminal
  eligibility. Python optimization is expressly rejected at `work():254`.

## Evidence and remaining limits

Independently rerun: **27 inherited checks + 15 old tests + 26 new tests PASS**.
Two additional pre-decision real-signal negatives reproduce P1. Two
post-decision signal cases characterize the documented boundary.

- [host_review.py](host_review.py): reproducible host-only review and signal
  scheduling hook; no DUT or producer prepare/work calls.
- [host_tests.log](host_tests.log): supplied 41 unittests pass, including the
  old/new cancellation comparison.
- [evidence.json](evidence.json): exact hashes, unchanged pins, loaded-module
  closure and four real-signal publication observations.

This is a launch review, not DUT acceptance or timing evidence. No current
Gather, NF8, final38, prefix5, service or worker status was queried. Parent's
reported Gather completion and NF8 pilot start do not themselves satisfy the
future launcher's pinned runtime gates here. Uncatchable SIGKILL, disk failure
and a missing terminal record remain nonacceptance conditions. The old raw/
CSV limitations described in review01 remain, apart from the fixed source pin
and the newly enforced no-`-O` guard.
