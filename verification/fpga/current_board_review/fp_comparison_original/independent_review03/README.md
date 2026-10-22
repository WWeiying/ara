# Independent review 03 — FP2 plan07

**NO BLOCKER / CLEAR for the reviewed plan07 code and explicit final-snapshot
contract.** This is independent review clearance, **not launch authorization**
or evidence that current admission gates are satisfied. Parent retains launch
authority. No DUT was executed.

Reviewed plan SHA256:
`75b25fae4ebdd7e6c68d9e66ee72c1673e88efd91495fa03a144cb96996f6737`.
All **2,742 pins** matched independent SHA256 computations before and after
the host review. They include all predecessor06 pins unchanged.

Preserved predecessor hashes:

- Plan06: `396cca255723e58fb5ba089220ed94edbb09c5a9417a69ac81e044de0d54d1af`.
- Plan05: `f0edb7011fdd4a69e0b633f03fa94405c072b7874367b69e3ab864e570069667`.

Only `independent_review03/` and temporary host directories were written.
No producer prepare/work, build, DUT, service launch, active-job polling or
shared/sealed-file edit was performed. Supplied host fixtures override frozen
runner preparation/build/DUT methods with isolated temporary fixtures.

## Finding disposition

No open blocking findings were identified in plan07.

| Earlier finding | Plan07 disposition |
| --- | --- |
| Review01: unpinned live `integration/prepare.py` | Closed for this snapshot: helper and loaded production-module closure are pinned, with independent byte hashing. |
| Old CSV cancellation: PASS row despite INTERRUPTED run | Fixed: sticky abort converts late rows to CANCELLED; terminal acceptance also requires COMPLETE and exact two PASS/rc0 records. |
| Review02 P1: separate pending-signal sample and later decision | Closed **for07 under its explicit kernel-snapshot contract**; plan06 remains blocked and its evidence is preserved unchanged. |

## Final signal boundary

Reviewed code: `../replay_restart_atomic.py:71–94`.
Reviewed contract: `../candidate04_restart_plan07/README.md:30–43`.

Publication requires the main thread and no remaining registered Python
worker threads (`:74–75`). Both JSON alternatives are serialized outside the
abort lock (`:76–80`). SIGINT/SIGTERM are then blocked, and the short locked
region checks single-use publication and evaluates:

```python
passed = eligible and not self.is_set() and not (signal.sigpending() & SIGNALS)
```

Every possible PASS path reaches the final current pending-set query. There
is no reused early sample. Ineligible/latched paths can short-circuit only to
nonacceptance. The linearization point is the **kernel pending-set snapshot
inside that query**, as the pinned code comment and README state. The later
Python return, assignment and atomic rename are not the decision boundary.

Consequently, a SIGINT/SIGTERM already pending at that snapshot vetoes PASS.
A signal arriving after the snapshot can set the latch when unmasked while
the committed result remains PASS. This is intended and explicitly documented
after-decision behavior, not a claim that every signal before rename vetoes
acceptance. This definition resolves the inconsistency reported for06.

The frozen runner's ThreadPoolExecutor context exits and joins its workers
before run returns; `work():279–296` completes returned-row/summary checks,
pin/image/module/approval/gate checks and calibration reads before publishing.
The outer signal context remains installed throughout. No worker is started
between the main-thread publication guard and its decision in this path.

## Independent host evidence

All **27 inherited checks + 47 unittests** passed independently. The47 comprise
15 scope/resource tests and32 atomic-runner tests (26 inherited cancellation/
runner tests and6 new signal-boundary tests). The inherited26 are actually run
against the07 implementation by the test subclass's scoped module replacement.
The old-checker negative still returns PASS with INTERRUPTED metadata; the07
checker returns CANCELLED with INTERRUPTED metadata and cannot pass the
COMPLETE/exact-two terminal gate.

Additional independent testing swept **22 real-signal opcode cases**:

- For each SIGINT and SIGTERM, injection at every opcode of the final Boolean
  expression through the actual `sigpending` CALL: **20 total rejection cases**.
  Each signal was kernel-pending while no terminal file existed; all produced
  NOT_PASS. No signal state, abort method, publication or rename was mocked.
- Injection at the first opcode after that CALL: **2 after-decision cases**;
  both produced PASS, consistent with the documented snapshot boundary.

The supplied six new tests also passed, including wrappers that call the real
kernel query, send a real signal after its snapshot, and return the unmodified
snapshot. These establish the intended distinction between sampling and
function return; they do not fabricate a pending set.

Four additional guard checks passed: a live Python worker prevents
publication; a non-main caller is rejected; ineligible and already-latched
paths both publish NOT_PASS without needing a final pending query.

Evidence:

- [host_review.py](host_review.py): independent hashes, test rerun, opcode sweep
  and thread/short-circuit guards.
- [host_tests.log](host_tests.log): all47 supplied unittests PASS.
- [evidence.json](evidence.json): plan/predecessor hashes, unchanged2,742 pins,
  loaded production-module closure and each opcode/signum outcome.
- [findings.json](findings.json): machine-readable conclusion and scope.

## Preserved execution and acceptance gates

The07/06 runner diff was inspected. Beyond successor paths/preparation
lineage, functional changes are the publication thread guard and final query
expression. Both case entries and held682 entry equal06 exactly. Scope remains
two original130-call ELFs with the complete unchanged oracle/assembly/fixtures,
jobs2, 3600seconds per case and no build. Held682 cannot enter the test list;
no942-call acceptance is possible. The existing dry-run metadata contains only
the two DRY_RUN records and enables the complete commit trace.

Raw failure veto, exact PASS/count/tohost0/finish checks, full frozen trace
validation and target retirement counts retain the previously reviewed paths.
CSV/hash checks remain outside the terminal lock. Exceptions and negative
results latch cancellation, and the frozen runner's process-group cleanup
remains responsible for terminating simulators. `terminal_inputs():195–207`
requires COMPLETE, exactly PASS:2, exact matching names, rc0 and artifact paths.

`integration/prepare.py` retains its reviewed hash and all loaded production
project modules match pins (the independent review harness is excluded from
the production module comparison). `verify():125–132` hashes bytes directly.
Process inventory still recognizes `comm == simv` **or** argv0 basename `simv`
and uses inherited cap24/reservation/memory accounting.

Authorization, fresh one-shot output, pinned evidence, exact38/Gather release,
NF8 admission and before/after identity gates remain. The review template
retains prefix5 unit `ara-arithmetic-prefix5-candidate04-01.service`.
The outer4500 limit remains supplied by the parent-owned systemd command,
with TimeoutStopSec120/KillMode=control-group/Restart=no; it is not enforced
internally by Python. Python `-O` remains rejected.

## Residual limits

- Clearance applies to this exact plan/code and the documented final-snapshot
  ordering. It does not retroactively clear plan06 or change its P1 evidence.
- `threading.enumerate()` establishes the absence of registered Python
  workers, not an OS-wide proof against foreign native threads. The inspected
  standalone runner path joins its executor and has no added native-thread
  producer; introducing one would require re-review of signal delivery.
- After-snapshot signals deliberately do not revoke the committed terminal
  result. Uncatchable SIGKILL or an exception preventing terminal publication
  provides no accepted completion evidence.
- This review did not query current services/workers, Gather/NF8/final38
  terminal state or available resources. Parent must still supply and approve
  actual unit/evidence identities and satisfy runtime admission. Resource
  observations remain coordinated snapshots, not a global atomic reservation.
- No new DUT correctness, throughput or timeout guarantee is claimed. Earlier
  scoped raw/CSV evidence limitations remain; this review addresses the07
  successor and cancellation/source-identity corrections.
