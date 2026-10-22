# Independent Collected-Unit Review 08

Verdict: **CLEAR / NO BLOCKER for the narrow plan08 dependency-gate successor.**
This is independent launch-gate review, not DUT acceptance or launch execution.
Parent approval must bind the exact plan below and a fresh parent review JSON.

## Reviewed Identity

- Plan: `candidate04_restart_plan08/plan.json`
- Plan SHA256: `011540f110776d0c9296924f6d677f6c43ce8619ebaabd1f4b93d8f77b5b054a`
- Entrypoint: `replay_restart_units.py`
- Dependency helper: `restart_dependency_gate.py`
- New unit: `ara-fp-original-restart-candidate04-02.service`
- New output: `candidate04_restart_run04`
- All 2750 plan pins verified. Frozen M4 image/source identity and the loaded
  21-module pin closure verified. Sealed plan07 hash remains
  `75b25fae4ebdd7e6c68d9e66ee72c1673e88efd91495fa03a144cb96996f6737`.

## Root Cause And Narrow Fix

The actual plan07 service log begins `Failed to connect to bus: No medium found`.
Its entrypoint sanitized away XDG/DBUS variables; rc1 was not proof of a
collected service. This failure occurred before creating the run directory.

The successor obtains a trusted local user-manager environment from getuid,
validates runtime-directory ownership/permissions and bus-socket ownership/type,
and passes this environment explicitly only to the bounded systemctl query.
It does not weaken or mutate the simulator's sanitized environment.

Exact pinned terminal records are checked before interpreting service state.
Gather membership uses the exact 75 runner names from its sealed plan, not the
different source-name namespace. Both Gather75 terminal/worker and exact38 PASS
are bound to their plan hashes; NF8 admission and parent approval remain required.
The structured seven-property check rejects active, unknown, malformed, bus-error
and ambiguous responses. A narrowly accepted not-found response requires
inactive/dead, zero MainPID/ControlPID and an empty ControlGroup. All-process
cgroup membership and unit-directory absence are checked separately.

## Independent Live Checks

At Unix time 1791719669, with XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS absent
from the review process environment, the actual successor query and full gate
passed against real terminal evidence. The existing plan07 parent review was
modified only in memory to substitute the exact plan08 hash and new FP unit;
this fixture does not create or substitute for parent plan08 authorization.

- Gather75 and final38: rc0, not-found/inactive/dead, MainPID=ControlPID=0,
  empty ControlGroup, no stderr.
- All-process absence scan: 1200 processes examined, no owned process or unit
  cgroup directory for those dependencies.
- Old FP unit `ara-fp-original-restart-candidate04-01.service`: loaded/failed/
  failed, zero MainPID/ControlPID, empty ControlGroup; separate process/cgroup
  absence check passed. This confirms the prior launch attempt is terminal.
- Resource gate: whole6, NF7two, NF8eight, prefix5two, FPtwo reserved; total20
  against cap24, no unknown simv, MemAvailable194996842496 bytes.
- The ambient environment remained unchanged and sanitized. Both old run03 and
  new run04 directories were absent; no DUT was launched by this review.

## Regression Preservation

Independent in-memory property-parser checks passed five accepted cases and
twelve rejected cases, including bus failure with empty or apparently complete
stdout, unexpected stderr/status, active unit, nonzero PID, residual cgroup,
wrong identity and duplicate properties. No test main or sealed-output writer
was invoked. Prepared host evidence records 27 inherited checks plus75 unittest
checks; those full suites were not rerun by this reviewer. Dryrun contains the
exact two required programs, both DRY_RUN.

AST comparison against sealed07 confirms AbortLatch, process identification,
scan_simv, resources, runner_class, execute and terminal_inputs are unchanged.
Thus initial and per-dispatch resource call paths, full original130-call oracles,
target-count validation, sticky abort and terminal publication logic are retained.
The 682-call case remains held. No result is promoted to full942 or Linux closure.

## Approval Boundary

The narrow successor is cleared for the parent's fresh SHA-bound approval.
The existing jobs2, 3600s per simulation and externally enforced 4500s owning
service/cgroup contract remain required. Preserve plan07 and all sealed inputs;
do not reuse an active old service or existing output directory. This review
neither starts nor retries a DUT, and grants no broader verification closure.
