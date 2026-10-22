# One-Job M4 Plan

This document is a command reference, not launch authorization. The fixed plan
is `candidate04_plan01/plan.json`; only `fp_merge_prefix195` is executable.
The existing source/ELF/full original oracle are unchanged. No full21504 or
Linux acceptance is claimed. The original195 setup/target/return instruction
sequence is checked against frozen RVFI retirement, including the actual boxed
scalar FPR load, vsetvli VL, vstart/sticky writes, returned CSRs and raw exit0.
The frozen RegressionRunner and generic CVX/retirement validator remain in use.

## Read-Only Review

`python3 -B verification/fpga/current_board_review/fp_merge_original/replay.py audit`

This verifies the fixed contract, all115 preparation pins plus consumed frozen
sources/image and Python dependencies. It invokes no DUT, build, or writer.
Preparation records one DRY_RUN and focused host tests. Synthetic trace fixtures
test the checker only and are not instruction/DUT execution evidence.

The imported, reviewed `restart_dependency_gate.py` supplies a validated local
user-bus environment for systemctl only. Exact38/Gather terminal evidence and
NF8 initial admission remain pinned. Initial and per-dispatch resource checks
charge the fixed prior20 reservations plus this one:21/24, plus unknown or
over-quota simulators. MemAvailable must be at least32GiB. Admission fails rather
than polling/retrying; parent may wait for NF7/resource release before launch.

## Parent Approval And Command

Parent must create a NEW review JSON from `candidate04_plan01/review.template.json`
with only `parent_authorized` and `reservation_coordination_confirmed` changed
to true, then bind its SHA. Keep plan inputs sealed. Do not run preparation again.
Run the following only after independent review and explicit parent approval:

```sh
ROOT=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/fp_merge_original
REVIEW=/absolute/path/to/parent-approved-review.json
PLAN_SHA=$(sha256sum "$ROOT/candidate04_plan01/plan.json" | cut -d' ' -f1)
REVIEW_SHA=$(sha256sum "$REVIEW" | cut -d' ' -f1)
systemd-run --user --unit=ara-fp-merge195-candidate04-01.service \
  -p RuntimeMaxSec=9600 -p TimeoutStopSec=120 -p KillMode=control-group -p Restart=no \
  -p StandardOutput=append:$ROOT/candidate04_service01.log \
  -p StandardError=append:$ROOT/candidate04_service01.log \
  /usr/bin/python3 -B "$ROOT/replay.py" work --authorize-run \
  --approved-plan-sha256 "$PLAN_SHA" --review "$REVIEW" --review-sha256 "$REVIEW_SHA"
```

Verify the displayed plan SHA against the independently reviewed hash before
using this command. The service directly owns the worker and descendants.
Existing output is refused; no simulator retry or output reuse is permitted.
Check the owning service properties and actual one-simv advancement once, then
inspect after terminal completion rather than repeatedly polling.

## Budget And Acceptance

Test9000s; owning service9600s (2h40m), with120s stop grace. Spike retired3,382,750
instructions. Parent's approximately800-retire/s FP130 startup sample would
imply about4228s before other costs; this is not full-runtime measurement or a
completion promise. The larger fixed limits include margin, not permission to
increase them automatically after a timeout.

Sticky cancellation extends through trace validation, pin rechecks and atomic
publication. PASS requires one COMPLETE/PASS/rc0 result, exact original195 raw
markers, no failure/trap, generic trace validation, all195 target states and
original return sequences, zero-tohost/finish and unchanged inputs/image.

After the service is terminal, run the independent no-write raw audit:

`python3 -B "$ROOT/replay.py" terminal-audit`

Also reject a service timeout/abort/nonzero exit externally even if a terminal
JSON exists. Plan preparation and the audit mode confer no launch authority.
