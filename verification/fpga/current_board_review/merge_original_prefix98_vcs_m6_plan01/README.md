# Original Integer Merge98 M6 Plan

Prepare/dry-run only. No launch, RTL build, compiler/reference invocation,
FSDB or retry. All files here are new owned successors; reference, independent
audit and existing shared helpers remain unchanged. The actual plan and
ready.json provide final hashes and commands after Host gates finish.

## Exact Scope

Use only the accepted SoC ELF from ../merge_original_prefix98_prepare01:
`soc01/merge_prefix_e16_m8_ops4.elf`, SHA
4e495abc1ec6b553554c5ddee992db88234c969adcba2f92b90ed6c78ea245ab.
Same original98 calls,97 predecessors, cap512,50176 results,196 guards,
98 returned-vstart checks and13 helper instructions per call. Target is
SoC0x80000798:5c880c57. Preserve original vmerge.vvm selector semantics:
selector0 body elements take input[i], selector1 take indices[i]. Only
prestart/tail retain91; do not use gather inactive/OOR or scalar0 rules.

Frozen image (no build):
`/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`.
image.json SHA a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0.
Source manifest, frozen configuration, executable/image files and all snapshot
source hashes are verified and pinned by the existing image_context helper.

## Strict Gate

- Every actual retired PC and encoding must match the prepared ELF.
- All20 unused helper **complete byte ranges**, including internal integer
  and CSR instructions, are forbidden. Selected13 instructions must retire
  consecutively, from entry, exactly98 times; interior duplicates are rejected.
- Capacity is precisely the original3 instructions once. Seven outside-helper
  startup/C CSR instructions have exact order, operands/vlenb results and
  phases: six precede capacity, the original C vlenb follows it. RVV retirements
  are only capacity plus original helper windows. Legitimate vector-CSR CVX
  transport remains allowed by the frozen generic validator.
- Validate512 RNG/input/index triplets once, original3584 filtered iterations,
  each call's128 mask clears, each selected-bit pack write in order, all514
  destination/guard initializations and their memory byte enables. Check all
  a0..a7 arguments, full setup bytes, original vset returns and vstart writes.
- Require512 original scalar LHU results in order then both original guard
  sites, exact addresses/byte enables, and98 returned-vstart0. Missing upper
  tail or a final read cannot pass. This is scalar architectural evidence;
  no direct DUT vector-register payload or internal wave claim is made.
- Require original CTRL0 exit at actual store PC/address, then only original
  pure self-parking. Verify both raw logs, unique PREFIX98/case/replay/success
  markers, finish, generic full CSV consistency and private ELF/image/command.
- Reject actual partial RVV_PERMUTE_DETAIL immediately in the real frozen
  runner monitor, even without newline/final FAIL. Cancellation during strict
  validation latches abort through COMPLETE and atomic final publication.

## Reference Binding

Producer READY SHA:
8381b90ee089c90be273faca67b8096f802f628f655fd5756a186ef57b3ed175.
Actual independent ../merge_original_prefix98_audit01/admission.json SHA:
e4b71f9ce87aa77eb7b28db1b727164f6e52a28bd37acac070c41e790bb9ed75.
Actual REVIEW.md SHA:
7790c94990664706b86513c3508fa74f392942d861ba17b3cf1eb7a2dd3a4dd5.

The worker reads the real admission schema and its linked audit.json/audit.py
hashes, exact reference scope and all evidence pins. Its decision is
ACCEPT_SOURCE_REFERENCE_FOR_DUT_PLAN_BINDING_ONLY, dut_launch_authorized=false.
This is accepted source/reference evidence, not DUT or full-child acceptance.
No producer/auditor field is edited or falsely upgraded by this plan.

## Budgets And Resources

Fixed jobs1, seed1,9000s per case,10200s direct service hard limit,
KillMode=control-group,Restart=no. Whole exact98 scope; no automatic retry,
timeout expansion, oracle reduction, new image or FSDB.
Reference2020160 instructions/273 retired/s*1.2 gives8879.82s: only120s
margin inside the case budget. Different vector behavior/contention can make
this exceed the bound. Completion is not guaranteed.

Runtime admission scans comm AND argv[0] for simv, counts live external
workers once, adds this one job plus explicitly unused external reservations,
requires total<=24 and MemAvailable>=32GiB. No stale hardcoded whole59/NF
reservation is inherited. Prepare/dry-run do not query or claim live capacity.
Parent sets --reserved-slots at preparation;0 means no extra unused reservation,
not zero live external workers. Runtime checks actual resources immediately
before starting. A failed gate stops without a retry.

The worker must itself be MainPID of the expected active user service and
the exact cgroup. systemctl queries explicitly restore trusted per-UID
XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS after environment sanitization;
missing bus/unknown service never substitutes for ownership. A10200s service
stop cancels the control group. No collected-service defaults are claimed as
historical execution evidence.

## Commands And Authorization

Run from the integration worktree; these two modes never start a simulator:

```sh
python3 -B verification/fpga/current_board_review/merge_original_prefix98_vcs_m6_plan01/replay.py prepare --authorize-prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/merge_original_prefix98_vcs_m6_plan01/prepared01 --reserved-slots 0
python3 -B verification/fpga/current_board_review/merge_original_prefix98_vcs_m6_plan01/replay.py dryrun --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/merge_original_prefix98_vcs_m6_plan01/prepared01 --plan-sha256 PLAN_SHA
```

prepared01/ready.json will contain the exact future systemd-run command and
plan SHA. It is **not executed** by prepare/dryrun. A separately pinned parent
review must contain decision AUTHORIZE_MERGE_PREFIX98_ONCE, exact plan_sha256,
unit ara-merge-original-prefix98-m6-01.service, budget_risk_accepted=true,
reference_ready_sha256, reference_admission_sha256 and reference_review_sha256.
Only explicit run --authorize-run with that review path/SHA may proceed, after
independent runner review and parent authorization. No valid launch review is
created here. Final publication rereads the disk plan hash after expensive
checks/evidence hashing, validates pins/image, runner COMPLETE/PASS1, raw exit
and exact membership, and rejects sticky abort/pending termination signals.

## Host Evidence

host01.json is retained **FAIL_HOST_ONLY**: all24 strict negatives passed,
but the synthetic positive omitted CVX requests for legal vector-CSR
retirements. Generic validator counted1082 retired vector/CSR operations
versus883 fixture requests. This was a Host fixture transport error, not a
DUT/reference failure; no DUT was launched. The successor fixture uses the
same frozen generic is_vector_instruction classifier for CSR and RVV requests.
No strict checker condition was relaxed. host02.json is the successor result
required by prepare; absence/non-PASS blocks preparation.

Host fixtures use actual ELF PCs/codes and complete original model values,
but are explicitly synthetic protocol streams, not CPU execution evidence.
They cover selector-zero mask-off confusion, reversed source selection,
prestart/tail, last result/guard, wrong pointer/start/encoding, missing setup,
BE corruption, capacity/CSR duplication, unused helper interior and broken
contiguity. Separate tests cover raw monitor failstop, no-abort COMPLETE,
pending-signal publication, fresh disk plan drift, reference/parent gates,
resource limits and actual frozen RunOptions. No source references are rerun.

Acceptance remains one original-source prefix on M6 if later measured. Unknown
historical final tuple, full2688 child, Linux execution and other merge/stall
records remain unclosed regardless of this preparation result.
