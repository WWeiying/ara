# Automatic Terminal Successor

Prepared02 is the current candidate; prepared01 remains blocked, not launched.
No worker simulation, Host28, ELF compilation or reference was repeated.
The original worker88d7d147..., strict0bfc7055... and checker c3e5f084... are
unchanged. `replay02.py` is not used by either the ready command or collector.

| Input | SHA256 |
| --- | --- |
| prepared02/plan.json | b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd |
| prepared02/ready.json | 89c37924aefdcca6ada87dfb1430ce0bc8e6853c4827297eec10340b37e1339f |
| prepare_launch02.py | 5658f8d6cd516aa34b626a27dd19d5c7a9ca988f2ee27ab16cd69112738ba37c |
| exit_hook02.py | f24761dc2b37c7b1c018bfd907e4c43dbe91d34a43fbf5d71e547fb50ea6a669 |
| collect02.py | a692a72a5c51a783d2a3f38e0eea1250599fbef2a341265198122a7183894477 |

The750-pin plan binds the actual automatic service contract and both terminal
scripts. Fresh ready argv sets Type=exec, RemainAfterExit=no, KillMode=control-group,
Restart=no and RuntimeMaxSec13200. Simulator10800/worker12000/jobs1/cap24/mem32
remain unchanged. Stop-phase bound300s and collector bound180s leave headroom;
neither extends the simulator/worker deadline. The direct worker is the unchanged
`replay.py`, not a wrapper process hiding its PID.

On actual main-process exit, ExecStopPost first writes `service_exit.json` from
the systemd environment. Missing/unknown/nonzero main exit cannot be accepted.
Only actual success/exited/0 plus full producer PASS, durable simulator numeric0,
full17920 scalar/FPR/owner counts and unchanged bindings can produce the metadata
collector PASS. Its actual subprocess wait is separately persisted in
`collector.wait.json`. No second CSV semantic traversal is performed, and the
collector does not claim an independent numerical re-audit.

Actual preparation command was `python3 -B prepare_launch02.py`. This performed
fresh preparation and the unchanged runner's real dryrun. Unified exec session6468
returned numeric0, wait chunk `a003ab`; dryrun records one DRY_RUN and no console,
CSV, simulator or build output. `prepared02/dryrun_gate.json` binds the exact
runtime command. This receipt is tool-observed, not an inferred missing-process
success. No systemd service was launched.

Aquinas has the exact plan/ready/helper hashes for final review. The real
independent entry must bind the new plan while retaining original worker/checker
hashes. The subsequent parent run record should additionally include this ready
SHA and execute its exact argv. Initial actual-service observation should record
RemainAfterExit=no along with the original worker PID/cgroup/budget receipt.
Neither this note nor the ready placeholders constitutes launch authorization.
