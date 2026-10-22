# Conditional E16 Terminal Observer Review

**No blocking findings. APPROVE_CONDITIONAL_E16_MF4_TERMINAL_OBSERVER** for
READY `c741ea5647461c3ee6dec714a1adc96ddb250b16a7f4157c71dd26ca9fe292b3`,
pins `7030cd815dafce22f28d2ad9ef84c86ca7b7ae535010236a5f95566ea1a6d8e4`.
Hilbert/main may attach the one prepared observer under the parent's stated
authorization. This reviewer did not attach, launch, poll or query the live DUT.

## Verified Contract

- Rehashed all972 immutable pins, with no active result/CSV path in that set.
  Exact worker launch SHA binds PID1842515, plan17fc37..., entry962d5b... and
  parentd54061.... Current running-worker identity was reported by parent;
  this review did not independently query `/proc`.
- The successor diff against the known e32 observer changes only shape,
  approval/launch/PID identities, labels and totals. `one_pass`, `HashLines`,
  `outcome_gate`, `wait_fd` and `publish_success` are AST-identical. Stored
  Host8 is PASS with actual child wait0/0.467415448s; no Host rerun.
- Live attachment opens an actual pidfd, verifies exact worker argv/cgroup,
  records attachment identity and waits for exit using bounded `poll`, not a
  polling loop over simulation progress. An exit race fails closed. Missing
  process is never success by itself: the retained fallback requires durable
  terminal evidence and all later gates, and labels service exit unconfirmed.
- Before opening the CSV, the child requires exact whole1 COMPLETE/PASS,
  simulator numeric integer0 (not bool), unchanged plan/approvals/evidence,
  no abort/retry/error, exact private ELF/image/command, strict console/raw
  vetoes and an empty worker cgroup. A failed worker can cause a short metadata
  audit rejection, but cannot start a successful full CSV acceptance.
- One lossless full CSV traversal feeds the immutable generic validator and
  the previously reviewed e16 Strict checker, computing SHA from the same
  bytes. Header/row shape, full EOF and pre/post file identity are required.
  No row/event filtering, normalization or second CSV hashing pass is used.
- Exact full4095 call history,65520 results,8190 guards,4095 vstarts and53235
  helper instructions remain mandatory. Strict still binds the e16 model,
  original ELF helpers and frozen-M6 reset profile. Output must equal both
  the worker's strict report and generic six-event ledger, with balanced
  requests/responses and backend allocation/completion and no exceptions.
- Actual offline child wait status is saved before requiring return0/no
  timeout/no error. The child report alone is pending acceptance. Supervisor
  rechecks inputs/terminal/cgroup and publishes exclusively with late-signal
  protection. First failure is retained; no automatic retry or DUT rerun.

## Limits And Handoff

Wait14400s / audit900s / observer service15600s are separate observer bounds;
they do not increase the simulator10800s or worker12000s/service13200s limits.
PIDFD reports process exit, not a historical process wait code or systemd
service exit. The implementation consistently retains
`UNCONFIRMED_NOT_INFERRED` for that service evidence gap.

This is preparation/conditional-observer approval only. No architectural
terminal result, source-level PASS4095, Linux closure, or new actual startup
confirmation is claimed. No new tests, reference runs, raw parsing, build,
live process queries, or sealed-file changes were performed. Review metadata
and bindings are in [REVIEW.json](REVIEW.json); parent can relay them to Hilbert.
