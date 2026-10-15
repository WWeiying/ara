# Full E32 MF2 Standalone Preparation

Status: **FROZEN_PREPARED_NOT_ADMITTED_NO_DUT**. No launch occurred. Host,
prepare and dryrun subprocesses all completed with actual exit0. This is not
DUT acceptance, permission to launch or recovery of the old canceled trace.

## Scope And Gates

- Exact unchanged original SoC e32 mf2 ELF:
  `54931771b1ba6ade43ae776af14f52163323670ec8881dc2fc1f70fe1c6c994f`.
- Original full5985 calls,95760 results,11970 guards,5985 returned-vstart checks,
  77805 helper instructions,35 operations and3 seeds/global RNG in original
  continuous source order. Original source/reference/model remain unchanged.
- M6 image.json `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
  New e32-only profile binds exact spec/ELF/model and inherits reviewed reset
  proof; all32 integer GPRs initially zero only for this fresh M6 reset image.
  Legacy consume/finish are inherited unchanged. Unknown source still fails;
  no source is learned from wdata. No invented fflags oracle.
- Original fullSmall2 ERROR/NOT_PASS and e32 CANCELLED remain untouched and
  the historical complete.json is pinned. No old raw CSV was opened.
- New unit `ara-arithmetic-full-e32-mf2-m6-01.service`, jobs1, standalone abort
  event and cgroup; direct worker MainPID, KillMode=control-group, Restart=no.
  Case10800s / worker12000s / service13200s. No retry, build or FSDB.
- Numeric monitor returncode/timeout/failure/cancellation and actual command
  are persisted before generic or strict postchecks. Late plan/input drift,
  sticky abort and incomplete runner/trace/oracle outcomes reject acceptance.
- Resource check occurs only at runtime: live simulators + jobs1 + unused
  reserved_slots0 <=24 with existing memory floor. Main must coordinate any
  concurrent reservations; this preparation did not inspect live tasks.
- Slow historical estimate9564s, plus20%=11477s exceeds10800s. This risk is
  explicit and requires parent budget acceptance; no extension is implemented.

## Host And Dryrun

Host15 methods PASS; actual process exit0,51.186998s, timeoutfalse.
One full5985-call constructed stream was checked; its near-final state was
reused for final result/guard negatives without rerunning that whole stream.
Additional fixture reconstructs real e32 ELF _start, full BSS clearing,
jal at8000004e, main80000f52, ra80000052 and original C.SDSP s0 save. These are
constructed architectural rows derived from the executable, not claimed DUT
capture. The old checker reproduces its missing-initial-s0 rejection; the new
profile accepts the exact path and rejects wrong address/masks/value, unknown
source, mismatched profile/spec/model and missing original start.

Dryrun validates the frozen plan and emits exactly one private ELF command;
`prepared01/dryrun.json` status DRYRUN_ONLY_NO_PROCESS. No simulation, Spike,
reference reparse or build was run. The e8 metadata-only review request was
relayed via Zeno to Confucius/main; no second e8 CSV parse was requested.

## Frozen Identities

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json (873pins) | b75d801b6533b73bfa9127ff695b60642a421535f9528202b07248fc3f368c93 |
| checker.py | 380aaa3f1672e9480bc0b7a85b6744029f4db3fc0bddf78121e7835dacd35c7d |
| replay.py | 60a7d34aeb10931ec708479285ec80087cbebed61058380d9ebe4bf94e011dec |
| reset_profile.json | b0c5f3860c09ae2e63c661432f29ac0b31ced24e3a071656a8df8077178d6418 |
| host01.json | 35429b85ebcabeb679b2252b5ef708e55da26bda2595b4f6a0adc7971aeb3f48 |
| host_process_exit.json | 390feb293e6425ed306cd1d50c370452032693b633f5778f620ac28f437e36cc |
| prepared01/dryrun.json | 97e72107fed752d469c07df2501a13428e32b6f4a5d3125233f31c39a8d834bb |
| prepared01/ready.json | feb3ba36408f4ab68d725a75cc1c515e3a65932c90e828e381419699a2ddde09 |

Exact future service command is in prepared01/ready.json. Independent entry
and parent review paths/hashes must replace its placeholders; schemas are
documented in README.md and enforced by replay.reviews. No unilateral launch.
