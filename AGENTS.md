# Project Working Rules

## FPGA validated migration (2026-10-30)

- Continue FPGA migration in `/home/wangwy/openproject/ara_dsa` on `ara_dsa`.
  Do not create more development worktrees for this migration. Existing staging
  worktrees are historical inputs, not the active integration location.
- Use `hardware/docs/FPGA_OPTIMIZATION_HANDOFF_20261029.md` and
  `hardware/fpga/vcu118/migrations/qbs_akv_validated_20261029.json` as the
  hardware/software version contract. Ara delivery is `1e48e205df5cec34183222c36d22eb4858466810`;
  llama.cpp delivery is `da56aa750559c180d631b466de983ff2bb5d54d9`.
  Both repositories have the `qbs-akv-validated-20261029` delivery tag.
- Preserve unrelated uncommitted files. In particular, do not include the
  uncommitted AKV assembly in the validated SDK. Extract pinned SDK/runtime
  sources with `git archive` into build inputs when local files differ; those
  inputs are build artifacts, not additional development worktrees.
- The original `hardware/deps/fpu_div_sqrt_mvp` contains a non-delivery delta.
  Do not regenerate the candidate from unchecked local dependencies. Preserve
  those files and reconstruct locked dependencies plus registered patches in
  build inputs when regeneration is needed.
- The FPGA source candidate is not a new hardware acceptance. Rebuild and
  validate the bitstream before claiming these optimizations work on the board.
  Retain the single-worker and runtime admission/fallback requirements; do not
  assert NORMAL_MEMORY eligibility without checking board memory conditions.

## Current verification tool policy (2026-09-27)

- The user stopped use of Verilator. Do not restart Verilator builds, coverage
  replays, or associated queues unless explicitly reauthorized.
- Verilator-only run artifacts in this worktree were removed at user request;
  old coverage percentages are historical, not current auditable results.
- Preserve VCS/Spike results, RTL, and verification scripts. Do not infer
  authorization to run URG or change checkers from this cleanup request.
- The user subsequently authorized VCS code-coverage builds and DVE reports
  using `verification/coverage/run_dve_coverage.sh`. Use independent output
  directories, one compatible instrumented build per collection, and checked
  passing tests for the verified report. Do not use URG or Verilator.

## Verification branch ownership

- When a helper and its tests have been reviewed and pinned for execution,
  stop editing them until the consumer finishes. Use a successor file for later
  changes; never alter a sealed helper while another agent is preparing or
  collecting its evidence. Use agent-owned output names to avoid collisions.
- Before editing any file during a campaign, inspect the running workers'
  `source-pins.json` inventories, including inherited documentation pins. A
  Markdown file can be a sealed input even when it is not executable. Do not
  assume that documentation edits are exempt from the consumer's identity gate.
  Preserve a failed worker's original reports. A proven documentation-only
  drift may have a separate, explicitly scoped functional audit; it must never
  be relabeled as a clean original-worker PASS or used to relax code/image pins.
- A transient systemd service must own the long-running worker directly.
  `start_new_session=True` does not escape a service control group: the default
  `KillMode=control-group` can kill spawned background children when the short
  launcher exits. Capture service stdout/stderr, confirm the actual EDA process,
  and distinguish launch preparation from an executing simulator or reporter.

- Use `ara_dsa_signoff_integration` as the sole active verification branch and
  worktree. Do not maintain independent ongoing verification campaigns in older
  verification branches.
- Temporary bug-fix branches are allowed only with user authorization to fix
  the bug. Return reviewed fixes, regression tests, and evidence references to
  this verification branch before resuming the main campaign.
- In focused repair campaigns, stop dispatching on a new failure. In the
  explicitly authorized batch-coverage exploration mode, freeze RTL and retain
  each case's first-failure evidence, but continue independent cases after
  ordinary RTL mismatches, stalls, or bounded timeouts. Do not repair RTL during
  exploration. Group repeated failures for later user-authorized repair.
- Stop affected queues on image/configuration drift, unreliable checkers, or
  systemic environment failures. Report exploration coverage separately from
  coverage backed by independently checked passing cases; never count a failed
  case as verified merely because it exercised new coverage points.
- Preserve older worktrees until unique tests, scripts, evidence, and symlink
  dependencies have been inventoried and consolidated. Do not overwrite newer
  implementations with old files or count old-RTL coverage as current coverage.

## RTL debugging and performance investigation

- Do not debug by repeatedly changing RTL, parameters, timeouts, or software
  hints and rerunning simulations without a concrete hypothesis.
- First inspect the relevant RTL and software source, reconstruct the request,
  dependency, queue, execution, and completion paths, and verify the exact
  semantics of every counter or probe used as evidence.
- Form a falsifiable root-cause hypothesis before changing the design. State
  which cycle-level signals distinguish that hypothesis from the alternatives.
- Prefer one minimal, representative, and discriminating simulation over many
  trial runs. Use a bounded FSDB window and a focused signal profile when a
  cycle-level explanation is needed.
- Change RTL only after static analysis and measured evidence agree on the
  cause. After the focused test passes, run representative regression points
  to check correctness and performance impact.
- Do not poll simulations expected to run longer than ten minutes. Start them
  in an independent background directory, confirm that they are progressing,
  and inspect the result after completion.

## llama.cpp optimization integration

- Treat llama.cpp/GGML as the primary runtime. Prioritize model, quantization,
  attention-shape, and context-length coverage there; other runtimes are
  optional adapters and must not weaken existing llama.cpp support.
- Develop and measure an optimization first with a minimal benchmark using
  real llama.cpp model data. Do not tune only for synthetic inputs.
- When an optimization has reproducible benefit, stable numerical semantics,
  and applicability beyond one captured shape, integrate it into the
  llama.cpp/GGML RISC-V or Ara backend instead of leaving it only in the
  standalone benchmark.
- Backend integration must include runtime shape/type/capability selection and
  retain the standard RVV implementation as the fallback path.
- Keep benchmark and backend implementations derived from one kernel source or
  shared helper where practical, so performance experiments do not drift from
  the code used by real model execution.
