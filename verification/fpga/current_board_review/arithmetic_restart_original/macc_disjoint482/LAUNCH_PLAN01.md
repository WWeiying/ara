# MACC Selected2 Launch Handoff

**READY, NOT AUTHORIZED, NO DUT STARTED.** Parent must check actual fixed2
terminal before authorizing this plan. No fixed-service polling, resource
admission, image/ELF rebuild, or live launch was performed during preparation.

## Frozen Inputs and Checks

- Plan: `candidate04_plan01/plan.json`, SHA256
  `96b6aa302176fda36d2b684b00c8df3e136e172e9b1c62b65cac4bff72326a58`.
- Preflight: `candidate04_plan01/preflight.json`.
- Existing M4 image ledger: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- **22 host gate tests PASS; exact2 frozen-runner DRY_RUN; 821 pins verified.**
- Original selected01 manifest fields, source/oracle, ELF bytes and expected
  markers are unchanged. `SELECTED01.md` records authentic original identity and
  source limitations. Spike measured1,940,068 and1,396,805 instructions; no new
  reference execution was needed for this launcher.
- Unit: `ara-macc-boundary-candidate04-01.service`.
- Fresh output: `macc_disjoint482/candidate04_run01`.
- Jobs2, timeout7200s each, RuntimeMaxSec7800 (2h10min, below3h),
  KillMode=control-group. The600s outer margin is for teardown/checking, not
  additional simulation time. No retry or automatic waiting worker.

Local scripts use the existing frozen M4 runner and the reviewed sticky-abort
structure. The reviewed fixed checker is imported read-only with its exact
SHA pinned solely for predecessor acceptance; no sealed other-agent source is
edited or monkeypatched. The runner's in-process fail regex is extended without
changing its on-disk source, as in the established launchers.

## Fixed2 Release and Resources

The parent creates a **new** review from `review.template.json`, retaining exact
plan/image/unit identities and setting `parent_authorized`,
`fpmerge_unit_parent_confirmed`, and `fixed_terminal_parent_reviewed` true only
after review. Set `fixed_disposition` to one of:

1. `ACCEPTED_PASS`: `fixed_evidence` must contain exactly `launch` and `complete`,
   each `{ "path": "<exact fixed candidate04_run01 path>", "sha256": "..." }`.
   The worker independently verifies fixed plan/launch/complete linkage, exact2
   COMPLETE/PASS/zero exit, full raw markers/veto, actual private ELF/image and
   preload identities, all fixed pins, and recomputes the original24-instruction
   fixed CSV audit against both stored audits. Missing terminal data cannot pass.
2. `FAILURE_HOLD`: parent must supply a nonempty `fixed_failure_reason` and exactly
   the authenticated `launch` evidence. This permits deliberate hold after failed,
   timed-out, or unresolved fixed data when complete.json may be absent. It does
   **not** accept fixed data or relabel unknown as RTL FAIL. Parent judgment is
   explicit and review-hash pinned; a missing/active run is not auto-released.

Both dispositions then require a trusted user-bus query showing no main/control
PID and terminal inactive/dead or failed state, plus an independent all-process
and cgroup-tree absence check. Collected/not-found units are not evidence of
success: they are usable only after authenticated launch and the parent decision.
No journal access or service exit success is inferred from absence.

Only then is fixed2 replaced by macc2. Exact reservations are whole6 + NF7two +
NF8eight + prefix5two + FPtwo + current FP-merge1 + MACCtwo =23. Current FP-merge
unit is `ara-fp-merge195-candidate04-01.service`, not the earlier proposed name.
Any remaining fixed simv rejects launch. Known groups use max(actual,reserved);
unknown simv are additionally counted, never hidden. Total must be<=24 and
MemAvailable>=32GiB. Admission runs once at launch and once per case; any refusal
stops without retry. No external process is stopped or modified.

## MACC Acceptance

Retirement CSV checks exact13 original instruction PCs/opcodes, exact1/2 helper
calls, original a/b/out+1/mask addresses, VL512, vstart256 for single481 and
vstart1 then256 for pair480-481, rm0, original b[0]=0 scalar load, and full returned
vstart zero. Traps, missing/extra instructions/calls, wrong order/start/VL or return
CSR fail. CSV does not expose vector result values: the unchanged firmware checks
all512 elements and both guards for every call and its original returned-CSR
container. Exact original summary/selection/board markers, begin marker, selected
indices, simulator success/$finish and exit0 are all mandatory.

Raw RVV_*FAIL (including FAILED), MACC_*FAIL, traps, unsupported/fatal/error tokens
veto PASS. The inherited runner also checks run.vcs.log and stops on raw failure.
Any case failure, timeout, read/CSV/identity exception sets sticky sibling cancel.
Late abort or pending termination signal prevents terminal PASS after individual
rows. Terminal requires COMPLETE, exact2 names/statuses/exit0, final input/image/
module pins and unchanged approval. Raw/CSV/input identities are retained in the
terminal record. This is source-selection acceptance only, not482-prefix or
original Linux stall closure; earlier vector history remains skipped.

## Parent Launch Form

After parent terminal review, create a new `parent_review.json` (do not rewrite
the template or sealed inputs), compute its SHA256, and use the approved plan SHA
above. The following is a handoff form, **not executed by this preparation**:

```bash
systemd-run --user --unit=ara-macc-boundary-candidate04-01.service \
  --property=RuntimeMaxSec=7800 --property=KillMode=control-group \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/arithmetic_restart_original/macc_disjoint482/replay_selected.py \
  work --authorize-run \
  --approved-plan-sha256 96b6aa302176fda36d2b684b00c8df3e136e172e9b1c62b65cac4bff72326a58 \
  --review /absolute/path/to/parent_review.json --review-sha256 REVIEW_SHA256
```

Parent must ensure no existing unit/output collision and may configure append
stdout/stderr logs outside pinned inputs. Worker checks its actual service cgroup,
RuntimeMaxSec and KillMode before creating a fresh one-attempt output. It never
launches without the explicit review/hash/authorization arguments. Parent handles
one actual startup confirmation; no polling loop is provided.
