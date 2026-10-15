# Actual Prepared01 Plan, No DUT Admission

Status: `PREPARED_NOT_ADMITTED_NO_DUT`; final plan ENTRY review and parent run
authorization remain unresolved. Main explicitly reauthorized prepare-only
after the actual Confucius code re-review cleared both ENTRY blockers.

## Actual Artifacts

- prepared01/plan.json SHA:
  `5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb`
- prepared01/ready.json SHA:
  `bd3cb160c92ba1869819f2f8effa25a584975eaaefa61861e9ba43777d4625e4`
- prepared01/dryrun_gate.json SHA:
  `af64e76213337a0a4e89b767fe3dd08ce501e9ba0ec0182cf786766f3b0f9742`
- actual dryrun command.json SHA:
  `ebc46010a2bb0daddba95d8c3ceae9ab60a395ff31bd806783d3ec02565343f0`
- Host03:55 tests,0 failures,0 errors; SHA:
  `21ae2b05eec4da2ffbc3cf5c3443246e84a09c928b710e7ff4f929b2fe0813b0`

Plan pins contain744 actual source, worker, Host, auditor, execution, original
binary proof and frozen M6 image inputs. Full pin table lives in plan.json.
Source READY02=11aec353..., independent audit=3a9c5276...,
REVIEW=08bc0bd4..., independent execution=a4197c53...,
original proof=7cc7582e... are explicitly bound to their actual schemas.
Image.json SHA:
`a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
Snapshot SHA:
`3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.

## Exact Service Command And Resource Contract

The complete shell command and worker argv are preserved in
prepared01/ready.json under service_command and command. It directly runs the
frozen worker via systemd-run --user, unit
`ara-gather-e8m4-vi31-prefix66-m6-01.service`, RuntimeMaxSec=6600,
KillMode=control-group, Restart=no, append stdout/stderr to prepared01/service.log.
There is no short daemonizing launcher. Parent review path/hash in that command
are visibly unresolved arguments, not invented approvals; the command was not
executed.

One testcase/jobs1/seed1, case5400s, outer6600s, reserved_slots0 (unused, not a
live count). Runtime admission remains deferred until a separately authorized
run:total<=24 and available memory>=32GiB. The source1353294 retirement count at
a600/s proxy is about2255s, not a completion guarantee.

## Single Dryrun And Freeze

One dryrun completed DRY_RUN_ONLY_NO_DUT. The actual frozen parent used its
dry_run branch, while an owned subclass bypassed its build method. Runtime
`+TESTCASE=gather_prefix_e8_m4_ops3`, original source label kept separate,
SoC source ELF4d2f9139..., NO_FSDB and COMMIT_TRACE command identity verified.
Dryrun preload points to the pinned source ELF by the frozen parent's actual
dryrun semantics; no private DUT execution or architectural result is claimed.
Future actual monitor command must use the runtime's private input.elf/CWD,
as enforced by the frozen worker hook.

No console, commit trace or VCS run log exists in the dryrun artifacts.
Final source/image/plan pin gates passed again, and plan SHA remained unchanged.
No VCS, Spike, compiler, image build or systemd service was launched. Source and
reference files were untouched. Host01, failed Host02 and Host03 are retained.
All plan-consumed worker/checker/model/Host/README files are now frozen and will
not be edited while the plan is consumed. This new handoff is not an executable
input and does not change the plan's pin table.

The actual plan hash, ready artifact/service-command path,744 pins and Host03
summary were sent to main for forwarding to Confucius's final plan ENTRY review.
