# Successor02 Review Entry

Status: implementation and host negatives ready for independent review; NOT
launch approval. The original `vcs_jobs8.py` is preserved, including its known
timeout/aggregate bug. Its host-only reference validation remains usable.
Only `vcs_jobs8_successor02.py worker` may execute a future reviewed plan.

## Changes and Linearization

- Per-group deadline state and acceptance share the scheduler's reentrant
  abort lock. A timeout sets a persistent latch and abort before acceptance.
  The acceptance path also checks monotonic time, so a delayed timer callback
  cannot allow a group that already exceeded2520s to pass.
- The group acceptance edge is the locked deadline/abort check followed by
  marking its terminal state closed. A timer after that edge is stale. An
  in-flight callback must finish first or the acceptance must finish first;
  `cancel()` is followed by `join()` before returning a group result.
- Cancellation reentering group file publication is detected and the owned
  complete artifact is atomically replaced with FAIL. A group that was already
  accepted before a different group's cancellation may remain PASS, but the
  campaign can never accept that cancelled run.
- Aggregate PASS requires exact48 membership, all group PASS, no timeout,
  no abort reason and unchanged post-run identities. At final publication,
  SIGTERM/SIGINT delivery is temporarily blocked and pending signals checked
  before and after publication. Cancellation during publication forces
  NOT_PASS/return1. The campaign terminal edge follows publication and the last
  pending-signal check under the abort lock; subsequent signals are post-run,
  not retroactive cancellation of a completed campaign.
- `support.save()` remains exclusive-create and unchanged. Successor-owned
  plan/template and terminal replacement use an explicit same-directory
  temporary JSON, flush/fsync, and `os.replace`. No sealed input is replaced.
  Pending temporary files are cleaned even on error. Terminal acceptance still
  requires the service to terminate successfully; a live complete.json is not
  independent final acceptance evidence.

## Host Tests

`python3 -B test_successor02.py`:14 tests PASS. These include:

- Real successor group_worker, mocked runner rc0, timeout inside checker.finish:
  group FAIL, timeout latch true, firstfailure exists.
- Same rc0 path with signal cancellation: group FAIL and cancellation retained.
- Expired clock with timer not yet scheduled: FAIL.
- Concurrent in-flight timeout versus acceptance, and stale post-commit timer.
- Actual filesystem PASS replacement following reentrant cancellation.
- Last-group timeout/all48 statuses PASS cannot produce aggregate PASS.
- Late cancellation with all runner returncodes0 yields NOT_PASS/return1.
- Real SIGTERM delivered during atomic aggregate publication yields a real
  NOT_PASS file and return1 after unmasking, not merely a mocked overwrite.
- Preexisting plan and review.template written with exclusive save are
  successfully replaced and their hash binding independently read back.
- Clean group/aggregate controls and post-pin-drift refusal.

The existing9 scheduler/capacity tests remain mandatory in preflight. No
fixture, ELF, oracle, reference campaign, image, budgets, membership, or
resource reservations changed. Full48 host CSV acceptance remains a separate
mandatory gate, not implied by these orchestration tests.

## Preflight and Review

After host-all192 is terminal PASS:

```
python3 -B vcs_jobs8_successor02.py preflight --out vcs_jobs8_plan02 --host-root dut_host_all192_01
```

The successor pins its source,14-test source/log, this note and the original
independent blocking review in addition to every base input. The ready plan
has `orchestration=deadline_cancel_successor02`. Worker requires that identity
and an explicitly authorized review.json binding plan/image SHA, exact units,
plus the path/SHA of the independent no-blocker review. A ready plan alone
does not authorize launching. New independent findings remain blockers.

Reviewed reservations: NF7=2, parent38=4, gather=4, whole=6, NF8=8, total24;
minimum32GiB available. Exact parent-supplied units are:

- parent38: `ara-candidate04-arithmetic38-03.service`
- whole: `ara-whole1134-candidate04-01.service`
- gather: `ara-gather75-candidate04-01.service`

After all review gates pass, the previously conditional authorization permits
`ara-nf8-full192-candidate04-01.service`, directly owning the successor worker,
RuntimeMaxSec18000, KillModecontrol-group, Restart=no, local append stdout and
stderr. Pilot0 first, then47 groups max8,2400s simulator/2520s group limits.
One live admission and one bounded pilot progress confirmation; no retry.

## Historical Results

See `LEGACY_TIMEOUT_AUDIT01.md` for the selected4 read-only artifact audit and
the extra mandatory NF7 terminal acceptance conditions. Do not edit running
NF7 helpers, trust its old aggregate alone, or rerun old cases to hide evidence.
