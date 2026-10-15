# FP2 Plan07: Prepared, Not Launched

Plan SHA256: `75b25fae4ebdd7e6c68d9e66ee72c1673e88efd91495fa03a144cb96996f6737`.

This supersedes the **blocked** plan06, without changing its files or plan05.
The independent06 finding and real-signal reproduction remain in
`../independent_review02/`. Plan07 needs its own independent review and
parent authorization; preparation is not launch authorization.

## Preserved Scope

Two exact original130-call ELFs, full unchanged oracle/assembly/fixtures,
jobs2, per-case3600 seconds, suggested service outer4500 seconds. The
682-call ELF and full oracle remain held, not shortened or executed.
No DUT result, build, RTL edit, or shared-helper edit in this preparation.

The raw failure veto, exact retirement multiplicities, sticky abort, exact
`run.json COMPLETE` plus `PASS:2` and matching two summary/returned records,
all source/image/helper pins, and comm-or-argv0 simv resource counting are
retained from06. Host tests:27 original checks plus47 unittest cases
(15 scope/resource,26 cancellation/runner,6 final signal-boundary cases).
The dry-run produced exactly two DRY_RUN records and did not execute simv.

## Final Decision Boundary

06 sampled pending signals and then made a separate PASS decision. A real
signal arriving between those operations escaped the sample. The preserved
review report proves that P1;06 must not be launched.

07 requires main-thread publication with all Python workers already joined.
It blocks SIGINT/SIGTERM over a short region and holds the abort lock.
The only PASS expression checks eligibility, the sticky latch, and finally
the **current** `sigpending()` set. Its linearization point is the kernel's
pending-set snapshot inside that last query, not Python assignment, syscall
return, or the subsequent file rename. Latch writes from other threads are
serialized by the lock; the main-thread signal callback cannot run inside
the blocked region. Expensive validation/JSON serialization stays outside.

Signals pending at that final snapshot veto PASS. Signals arriving after
the snapshot belong after the final decision, even if the Python function
has not returned or the atomic rename has not executed. This is explicitly
not a promise to veto every signal until rename. SIGKILL is not catchable;
absence of complete.json is never PASS.

Six new tests make this distinction reproducible for both SIGINT/SIGTERM:

- Opcode tracing injects real os.kill immediately before the final query:
  pending=true, no terminal file yet, then NOT_PASS.
- Injection immediately after the query: after-decision behavior, PASS.
- A wrapper calls real sigpending, then sends a real signal, then returns
  the unmodified kernel snapshot: also after-decision behavior. It does not
  fabricate pending-state or mock publication/rename.

The26 inherited tests run against the07 runner, including real frozen M4
executor/report writer and cancellation inside the actual130-row CSV
validator. Their intentional old-checker PASS row is a software bug
reproduction, not a DUT result.

## Launch Hold

Parent reports Gather75 terminal PASS and NF8 pilot started. Both remain
explicitly pinned admission evidence; no service was polled here.
The review template records prefix5 unit
`ara-arithmetic-prefix5-candidate04-01.service`. Resource reservations,
cap24 and32GiB floor are unchanged. Independent review target:
`../independent_review03/`.

After independent clearance and explicit parent authorization only, from
the fp_comparison_original directory:

```sh
python3 -B replay_restart_atomic.py work --authorize-run \
  --approved-plan-sha256 75b25fae4ebdd7e6c68d9e66ee72c1673e88efd91495fa03a144cb96996f6737 \
  --review /absolute/path/to/parent-approved-review.json \
  --review-sha256 PARENT_APPROVED_REVIEW_SHA256
```

Fresh output: `../candidate04_restart_run03/`. Use the explicitly approved
FP systemd unit with RuntimeMaxSec4500, TimeoutStopSec120,
KillMode=control-group, Restart=no. Never use Python -O. No automatic
682-call follow-on is implemented or authorized.
