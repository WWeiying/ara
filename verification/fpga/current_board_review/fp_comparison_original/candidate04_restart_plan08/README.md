# FP2 Plan08: Ready for Review, Not Launched

Plan SHA256: `011540f110776d0c9296924f6d677f6c43ce8619ebaabd1f4b93d8f77b5b054a`.

07's failed service and sealed inputs are untouched. Its service.log and
parent_review.json are pinned by08. The actual startup failure was
`Failed to connect to bus: No medium found`: the inherited environment
sanitizer removed XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS. Empty
stdout/rc1 did not prove a collected unit. No DUT was started by07.

## Narrow Change

`../restart_dependency_gate.py` supplies a trusted local user-bus environment
only to systemctl: getuid-derived runtime path, validated directory owner
and permissions, owned Unix bus socket. Simulator environment remains
sanitized. Resources use procfs/memory directly; there are no other
systemctl call paths in the successor.

Exact pinned38/Gather terminal evidence, matching plan hashes, completed
worker and exact75 program-ID membership are validated before unit queries.
Gather's plan.names is its executable-ID namespace; remaining_source_names
is a different original-source namespace and is not substituted for it.

The bounded query requires all seven properties and exact unit Id, zero
MainPID/ControlPID and empty ControlGroup. Loaded inactive/dead or
failed/failed requires rc0/no diagnostic. Collected not-found must be
inactive/dead with rc0, or narrowly rc1 with complete properties and only
an empty or exact unit-not-found diagnostic. Actual host observations use
rc0. Bus errors, missing/duplicate/unknown properties, active states and
other return codes reject. All processes' cgroup memberships and the full
cgroup-v2 directory tree are scanned; even an empty matching unit cgroup
rejects. Unreadable state fails closed, not as proof of absence.

## Verification

-27 inherited host checks and75 unittest cases PASS, including47 preserved
  scope/late-abort checks and28 dependency/environment cases.
-2750 pins unchanged; exact two DRY_RUN entries, no simv execution.
-After preparation, a separate once-only read-only complete gate check used
  the real pinned07 review, adjusting only plan hash and FP unit in memory.
  `dependency_preflight.json`: sanitized environment contained no XDG/DBUS
  variables; both completed dependencies were not-found/inactive/dead,
  no owned process/cgroup;20 reserved/live slots of24 and194867539968 bytes
  available. Image identity, loaded-module closure and pins also passed.
  This admission snapshot is not future authorization and is rechecked at
  real launch. No run directory was created.

Hilbert was sent the final path/hash for independent review. Parent retains
launch authority. No prepare/work/DUT rerun is needed for read-only review.

## Unchanged Scope and Future Command

Same two original130-call ELFs, complete original oracle/trace gates,
jobs2,3600 seconds each, outer4500 seconds.682 remains HOLD_NOT_RUN.
Late-abort semantics and signal-boundary tests are unchanged from07.

New unit: `ara-fp-original-restart-candidate04-02.service`.
Fresh output: `../candidate04_restart_run04/`.

Only after independent clearance and explicit parent approval, from the
fp_comparison_original directory:

```sh
python3 -B replay_restart_units.py work --authorize-run \
  --approved-plan-sha256 011540f110776d0c9296924f6d677f6c43ce8619ebaabd1f4b93d8f77b5b054a \
  --review /absolute/path/to/parent-approved-review.json \
  --review-sha256 PARENT_APPROVED_REVIEW_SHA256
```

Use the named unit, RuntimeMaxSec4500, TimeoutStopSec120,
KillMode=control-group and Restart=no. Do not use Python -O.
