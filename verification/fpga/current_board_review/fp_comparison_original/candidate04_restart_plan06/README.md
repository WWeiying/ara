# FP2 Successor06: Prepared, Not Launched

Plan SHA256: `396cca255723e58fb5ba089220ed94edbb09c5a9417a69ac81e044de0d54d1af`.

Sealed05, its runner, and all 2731 predecessor pins remain unchanged. This
successor adds six pins, including the previously omitted live
`integration/prepare.py`, the new runner/tests, and preparation evidence.
`preflight.json` lists the loaded project-module closure and all 2737 pins
were checked after the dry-run. Neither dry-run invoked simv.

## Scope and Budget

- Exact same two original 130-call ELFs, complete scalar/flags oracle and
  target retirement multiplicities. Jobs2, 3600 seconds per case, suggested
  service outer limit4500 seconds. No new DUT result or failure exists here.
- The unchanged 682-call original prefix remains `HOLD_NOT_RUN`; there is
  no executable path to schedule it in this plan. No942-call DUT PASS claim.
- No build, RTL edit, sealed-input edit, or edits to shared helpers.
- Parent reports Gather75 terminal PASS/no live workers and NF8 pilot started.
  Launch still verifies explicitly pinned evidence and inactive Gather/38
  services. Independent review and parent authorization remain required.
- Resource scan charges processes when either comm is `simv` or argv[0]
  basename is `simv`. Reservations and memory floor are unchanged: cap24,
  whole6/NF7two/NF8eight/prefix5two/FPtwo; memory at least32GiB.
  The review template sets prefix5 to
  `ara-arithmetic-prefix5-candidate04-01.service`.

## Late-Abort Evidence and Fix

`host_tests.log` records 41 unittest passes: 15 inherited plus26 new.
`host_gate.json` separately retains all27 original host checks.

The negative fixture invokes the real frozen M4 executor, signal context,
report writer, and original CSV validator. Only simulated DUT execution is
replaced by a completed oracle fixture. A separate thread sets cancellation
at CSV row65; the validator continues through all130 target retirements.

- Sealed checker: returned row `PASS/rc0`, actual run metadata `INTERRUPTED`
  with status counts `PASS:1`. This intentionally reproduces the review bug,
  not a DUT PASS.
- Successor checker: row `CANCELLED`, actual run metadata `INTERRUPTED`
  with status counts `CANCELLED:1`; terminal PASS is rejected.
- Additional tests cover cancellation during terminal serialization, after
  metadata validation, real SIGTERM during CSV validation, pending SIGTERM,
  forbidden latch clearing, raw failure/read exceptions, missing/incorrect
  run metadata, duplicate membership, and changed-comm capacity overflow.

The event remains sticky across runner return and all post-run validation.
The frozen runner's temporary signal handlers restore an enclosing handler
that remains installed through terminal publication. CSV/hash checks and
preparation of both terminal records happen outside the terminal lock.
Only the final eligibility/no-abort decision and atomic rename are locked;
SIGINT/SIGTERM are deferred across that short critical section, with pending
signals checked before the decision. That decision is the terminal
linearization boundary, not the earlier return of PASS rows. No guarantee
is made for uncatchable SIGKILL; absence of a complete record is not PASS.

Acceptance independently requires `run.json.status == COMPLETE`, exactly
`status_counts == {PASS: 2}`, exact two returned and summary identities,
both rc0, corresponding artifact paths, unchanged pins/image/approval/gate
evidence, and no latched abort. Raw failure veto and the full original
trace/oracle checks remain in force.

## Review and Future Command

Independent review requested in `../independent_review02/`; do not infer
clearance from the successful local host tests. The successor is
`../replay_restart_abort.py`, and fresh DUT output would be
`../candidate04_restart_run02/` (not created by preparation).

After independent clearance and explicit parent approval only, from the
`fp_comparison_original` directory:

```sh
python3 -B replay_restart_abort.py work --authorize-run \
  --approved-plan-sha256 396cca255723e58fb5ba089220ed94edbb09c5a9417a69ac81e044de0d54d1af \
  --review /absolute/path/to/parent-approved-review.json \
  --review-sha256 PARENT_APPROVED_REVIEW_SHA256
```

Run in the explicitly approved FP systemd unit, with `RuntimeMaxSec=4500`,
`TimeoutStopSec=120`, `KillMode=control-group`, and no restart. The review
must identify all seven actual units and their evidence hashes. No `-O`.
