# Fixed Boundary M4 Replay: Prepared, Not Launched

Plan SHA256: `9a31f50d44c245bc7439db5a462bac3eed54c2eecae74ffeae5931d3ea6995f0`.

Exactly `fixed_e8_m4_single776` and `fixed_e8_m4_pair775_776` from the
unchanged selected01 manifests. Jobs2,1800 seconds per program, service
limit2400 seconds; stop first failure. Existing M4 image only, no build or
RTL changes. No DUT launched during preparation.777-prefix acceptance is
explicitly false, regardless of future success of these two selections.

## Readiness

-11 focused host checks PASS (0.03s locally), including bad start/vxrm/
  sticky-vxsat, incomplete helper, raw failure veto, interrupted PASS rows,
  cancellation inside real CSV validation, pending signal and resource cap.
-Exact two DRY_RUN entries,807 pinned inputs/helpers/image/source artifacts
  verified unchanged. Actual execution uses frozen runner private input.elf;
  checker verifies its hash and exact PRELOAD command path.
-One read-only resource snapshot:23 live-plus-reserved slots,195179696128
  bytes available; no unknown simv processes. Reservations remain whole6,
  NF7two,NF8eight,prefix5two,FPtwo,fpmerge1,fixed2 even if observed use is lower.
  Both comm and argv[0] simv identities are counted. Resources are rechecked
  before launch and before each dispatch; no retry or capacity wait loop.
-No user-bus query is needed: no completed-dependency release is assumed,
  and resource checks use procfs/memory directly. The old20 reservations
  remain charged. No sanitized systemctl path is introduced.

`review.template.json` contains a **proposed** fpmerge unit. Parent must
replace it with the actual reviewed unit and set
`fpmerge_unit_parent_confirmed=true`, plus `parent_authorized=true`, in a
new approval file. The fixed unit must be
`ara-fixed-boundary-candidate04-01.service`; work verifies its own cgroup.

## Exact Acceptance

Full original oracle markers, raw failure veto (including MATRIX_FAILED),
rc0 and tohost0/$finish are required. The frozen runner validates the full
commit trace. The additional checker requires exact target counts1/2 and
all24 original helper instructions in order for each call. Retirement GPR
values bind VL/capacity512, vstart256 for776 or1 for775, vxrm0/3 and initial
vxsat0/1. Returned vstart must be0; returned saturation must match the
original fixture, whose source has no active min*min saturating pair.
CSR restoration must use the values saved by that call. Original trial
markers must be exactly776 or775,776, respectively.

Final acceptance additionally requires exact two returned and summary
identities, both PASS/rc0, run.json COMPLETE with exactly PASS:2, unchanged
pins/image/approval, and no sticky abort. Expensive checks remain outside
the terminal lock. Final publication retains the reviewed07 signal-pending
snapshot decision semantics; only the fixed-scope status label differs.

## Parent Launch Command

Only after read-only review and pinned parent approval, from this worktree:

```sh
systemd-run --user --unit=ara-fixed-boundary-candidate04-01 \
  --property=RuntimeMaxSec=2400 --property=TimeoutStopSec=120 \
  --property=KillMode=control-group --property=Restart=no \
  /usr/bin/python3 -B \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/fixed_restart_original/replay_selected.py work \
  --authorize-run \
  --approved-plan-sha256 9a31f50d44c245bc7439db5a462bac3eed54c2eecae74ffeae5931d3ea6995f0 \
  --review /ABSOLUTE/PARENT/APPROVAL.json --review-sha256 PARENT_REVIEW_SHA256
```

Fresh output: `../candidate04_run01/`. Do not relaunch into it, edit sealed
inputs, use Python -O, or treat this preparation as launch authorization.
Parent owns actual service launch/log capture and one-time startup check.
