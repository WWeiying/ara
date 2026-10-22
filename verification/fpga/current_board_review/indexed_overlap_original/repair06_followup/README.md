# M6 Followup Coordinator

Prepare only. No helper, RTL, fixture, or sealed output modifications.
This direct systemd MainPID owns one regression subprocess in the same cgroup;
it never creates another service. SIGTERM/first failure stops acceptance and
terminates its owned child; systemd KillMode=control-group covers descendants.
No retries or capacity waiting. Other jobs are counted, never terminated.

Wait at most10800s with120s sleeps for exact three-case M6 terminal PASS.
Before admission validate both pinned plans, original48 shared validator,
M6 image/configuration/source manifest, complete evidence membership and hashes,
all private ELF/input-image/commands, raw logs, complete per-case oracle ledgers,
runner summaries/exit codes and bounds. Require no predecessor worker/simv owner.
Active predecessor still waits; failed/timeout service refuses. A GC unit is
not historical exit proof: acceptance then relies on full worker/artifact evidence
and actual absent owners, with historical_service_exit_verified=false recorded.
Missing, partial, failed or aborted terminal data never admits regression.

The immutable ready regression plan selects original38 jobs4 then smokes10 jobs2.
It executes the sealed regression.py run command exactly, not a new helper.
Regression execution plus acceptance has21600s; all original per-case budgets
remain unchanged. Outer service33000s covers3h waiting +6h regression +600s
verification/teardown headroom. No external token polling is required.

Terminal statuses distinguish BLOCKED_PREDECESSOR, REGRESSION_NOT_ACCEPTED and
REGRESSION48_PASS. Signal cancellation may publish NOT_PASS, retaining phase.
Full CSV oracle recomputation is the predecessor worker's responsibility; this
coordinator verifies its complete hash-bound evidence/recorded oracle, not a
new independent architectural audit. Cycle-only performance changes retain the
sealed regression's review status and are not called performance equivalence.

Preparation commands from this directory (never launch):

```sh
python3 -B test_host.py
python3 -B coordinator.py prepare --out "$PWD/prepared01"
```

The generated service_command.NOT_EXECUTED.json is for parent review only.
Runtime requires --authorize-run and the exact coordinator plan SHA. Output
files are fresh/exclusive, all coordinator/helper/tests/source/image inputs are
pinned. Existing regression output must still contain no launch or completion.
