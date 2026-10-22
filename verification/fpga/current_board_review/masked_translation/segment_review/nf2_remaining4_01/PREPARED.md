# Sealed Prepare Handoff

Status: **PREPARED_NOT_ADMITTED_NO_DUT**. No VCS, RTL build or Linux execution.
Do not edit the pinned helpers, reference files or prepared plan. Parent owns
any future launch; reference acceptance alone is not worker/DUT admission.

- Plan: `prepared01/plan.json`, 700 pins, SHA
  `7a644bfd57e314649a92a6512cd6c994c49f7e9b656f0caaa5e172ec0e4d9c55`.
- One ELF / four cases, existing M6 image, jobs1, case6300s/service6900s,
  no retry/build/FSDB. Exact unexecuted direct-service command and review
  placeholders are in `prepared01/ready.json`.
- Dryrun: `prepared01/dryrun_check.json`, `PASS_DRYRUN_NO_SIMULATOR`, SHA
  `d027d96260a43db921670cfbfd68c5ef22ac4c3b469c204dcaa2f43e679e5cd2`.
- Reference READY SHA
  `d427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f`.
  Actual Aquinas REVIEW/result hashes are bound in the plan and launch gate;
  acceptance is source/reference only.
- SoC ELF SHA
  `cd2aa14f5251bf32353bf256b5c64e9035dc0ed266688bece78f7c691ac234d2`.
- Observer Host: `observer_host02/status.json`, two positive sequences
  (including allowed second-field fault address), 25 rejected mutations.
- Worker Host: `worker_host04.json`, seven tests PASS, SHA
  `e8662a9ce39e22c5900d4ac4a0fb83c04a66e3998c5ad46e72ba4f173b13cbe2`.
  Tests cover runtime/historical identity, seed/preload/cwd, missing oracle,
  ELF drift, budget/worker drift, checker-throw durable child rc and late abort.
- Worker `replay.py` SHA
  `3bf0e84546ef0c1ea275a8081eff63f09247e7df112c2801d62d2f877e3e57ca`.

`worker_host01.json` retains the initial Host-only Path/string fixture error.
Host02/03 were passing intermediate bindings; Host04 binds the final budget
and audited reference. No reference or DUT was repeated to fix Host metadata.

The final two all-off cases require only S-ecall, no fault retry, and full
memory checks before cleanup/refill. The original128B mask, fixture16B and
helper8B-consumed domains remain explicit in `REFERENCE.md`. These tests do
not prove Linux signal-frame behavior or byte-identical full Linux execution.
