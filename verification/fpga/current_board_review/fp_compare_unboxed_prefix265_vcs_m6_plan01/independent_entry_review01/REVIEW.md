# Unboxed265 Entry Review

2026-10-12. NO NEW BLOCKER FOR CONDITIONAL PARENT LAUNCH.
This is entry readiness only, not reference acceptance or DUT PASS.
Read/hash only; no Host rerun, reference parse, live query, build or VCS.

## Frozen Binding

- Plan: `e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940`.
- All733 plan file pins independently hashed: zero mismatches, including
  source/reference inputs and imported frozen execution dependencies.
- Runner: `f760f4a69190b29886f4fa70de289b992e052a46c0a6b6010dcc166792ea422a`.
- Checker: `48c233a86c5b26ef5196a26c845ec1374d8589f409a389193e1cdd53f2726cd8`.
- DUT strict: `b657f3606c9f0c0d64992ad3bc92c56e7646d81ed203d36d15cd8040d1052bfb`.
- Host02: `add04b1e985610c3f7e6b52af9fa110c32111470e03cd9db9c18b616df907491`.
- SoC ELF: `03e24bc51c28b705ae3cd373a51c38e04c39ab0eb26443d29ca7d36277741058`.
- Frozen M6 image ledger: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.

Direct diff against sealed reference strict.py is exactly the added
`s['spike'] and` guard around replay_log capture. No architectural check is
removed; SoC UART output is checked separately in console.log and VCS log.
The actual prepared spec has spike=false and binds the above SoC ELF.

## Checks Consumed

Host02 records5 methods,2 synthetic positives and13 case-specific negative
subtests, zero failures/errors,16.858139821328223s. Test source hash matches.
The positives use the real SoC specification and exercise both permitted-tail
choices. Negatives cover wrong unboxed equality, spurious NV, lost sticky,
VL0, guard, vstart, missing bit, duplicated/unused helper interior, encoding,
source input, argument pointer and exit. Lifecycle tests also exercise partial
DETAIL failstop, late abort and fresh-disk-plan drift. These are protocol tests,
not DUT evidence. Host01 remains historical failure evidence.

The checker retains265 ordered calls/264 predecessors,4587 helper instructions,
4240 result-bit checks,530 guards and265 flags/vstart checks. It checks setup,
capacity/bootstrap CSR phase, exact PC/opcode, contiguous helper windows,
unused op5..9 full ranges, raw-zero unboxed load, original fmv.d.x instruction,
exit and post-exit parking. Scalar DUT CSV does not prove internal FP payload;
full reference vector evidence remains the independent reference review's job.

Dryrun is one DRY_RUN result with null returncode, zero elapsed and the same
plan SHA. The adapter reuses the frozen worker with the current checker module
and overrides scope, validation, authorization, service identity and budgets.
jobs1/case5400s/service6600s; direct Python MainPID/cgroup checks, Restart=no,
no build/FSDB/retry. Existing immediate failure veto, sticky abort, COMPLETE
validation, late disk-plan/input checks and short signal-blocked atomic
publication remain in use. Runtime resource admission precedes runner launch;
no resource availability was asserted or queried here.

## Required At Launch

Independent reference is still pending. The parent approval must bind the real
audit JSON and REVIEW file by exact path/SHA, plus this plan, unit, budget
acceptance and READY
`ee10a401774a5cb474be69c317edad4ea052c147a42b5fd03aa4cc4b1f5db731`.
Current authorization_gate hashes those files, requires audit status
`ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT` and matching ready_sha256, and verifies
all READY baseline/owned pins before service/resource/runner execution.
Approval/reference pins are checked again before terminal publication.

The actual later audit schema and scope must agree with that contract; do not
invent acceptance or launch first and bind evidence later. This review does
not assert validation of additional dependencies that an unseen future audit
may introduce. A schema mismatch fails closed and requires explicit resolution.
No additional large Host or reference rerun is requested by this entry review.
