# Independent Review Request: Sealed Restart Plan05

Requested by parent after its structural review. This review is subordinate to
any existing NF8 final review assignment. No RTL, sealed-file edits, hardware
builds, DUT execution, service launch, or polling of active jobs are authorized.

Worktree: `/home/wangwy/openproject/ara_dsa_signoff_integration`.
Scope root: `verification/fpga/current_board_review/fp_comparison_original/`.
Reviewer may create only `independent_review01/` for findings and host evidence.
Do not edit shared root documents or this producer's sealed runners/plans/tests.

## Exact Inputs

- `candidate04_restart_plan05/plan.json`, SHA256
  `f0edb7011fdd4a69e0b633f03fa94405c072b7874367b69e3ab864e570069667`.
- `replay_restart_successor.py`: prepare/work adapter to the frozen M4 runner.
- `prepare_m4_plan.py`: inherited strict raw-console and full CSV checker.
- `test_restart_successor.py`, plan05 `host_gate.json`, `successor_tests.log`,
  `dryrun/run.json`, `dryrun/summary.json`, and `review.template.json`.
- The exact frozen runner/image/source files and original ELFs are in plan pins.
- Predecessor `candidate04_plan03/plan.json` must remain SHA256
  `f503af9bfac573987090e3ac1eea08f10f8e7768e390c757ea4e5095769caed6`.

## Required Review

1. Exact two original130-call ELF membership and unchanged full oracle/assembly;
   held682 entry remains complete but cannot enter execution. Only260 calls can
   be accepted, never942. Host/Spike PASS is not DUT acceptance.
2. Trace the actual execution path from work() through frozen RunOptions,
   RegressionRunner and result publication. Confirm no rebuild and exactly
   jobs2, per-case3600s; outer4500s is supplied by documented systemd command.
3. Independently assess raw failure veto, exact PASS/count/exit markers, nonzero
   return codes, missing/unreadable logs, assertion failures, exception handling,
   and cancellation of peers/queued work. Check that success markers cannot
   override a genuine earlier failure.
4. Check full CSV assumptions against frozen trace producer and existing sealed
   traces: order/cycle/trap fields, all130 target retirements (including VL0 and
   vstart>=VL cases), PC/opcode identity and zero-count other operations. Identify
   false-PASS and false-rejection risks, not just whether tests return PASS.
5. Check explicit authorization, approved plan/review hashes, before/after pins,
   one-shot output, Gather75 terminal/service/workers released, exact38 PASS and
   released workers, NF8 first admission, and cap24/MemAvailable32GiB accounting.
   Parent reports38 already independently accepted; do not poll other tasks.
6. Audit inherited27 host checks and15 successor checks. Optional focused
   additional host tests may write only the review directory or a temporary
   directory; do not call prepare() or work(), and do not rerun simulations.

Report findings by severity with exact file/line references. Include the plan
hash and a clear blocker/no-blocker conclusion with residual limitations.
Do not fix a finding yourself or modify plan05. Send the result to the requesting
task and write `independent_review01/README.md` (plus machine-readable findings
if useful). A review conclusion is not launch authorization; parent retains it.
