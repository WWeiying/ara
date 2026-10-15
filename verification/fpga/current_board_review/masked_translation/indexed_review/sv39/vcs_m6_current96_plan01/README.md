# NF7 M6 Full96 Successor: Preparation Only

This directory owns only a replay adapter, Host tests, and new preparation outputs.
No ELF/reference rebuild, RTL change, reference execution, DUT launch, resource
query, or service creation is part of preparation. Parent admission is separate.

## Exact Scope

Reuse the 24 immutable SoC ELFs in `../vcs_plan06/programs/programs.json`, in order
`nf7_g00` through `nf7_g23`. Each retains its original four ordered trials,
cases/status/symbols and accepted scalar ledger: 96 trials, 284816 comparisons,
168 checkpoints. The historical source label remains
`rvv_fault_replay_segment_nf7_indexed_e32_mf2`; it is never used as `+TESTCASE`.
The runtime label is the unique group ID. No recompilation or regrouping.

The unchanged `../csv_oracle.py` Checker runs in a separate observer process per
group, against the original symbols, cases, status and ledger. This preserves
geometry, instruction PC/code, full memory/guard/prefix/partial-field checks,
trap/PTE/SFENCE/same-PC retry order, completion magic and CTRL0. The isolated
process avoids module-global state crossing groups. A marker alone is insufficient.
This is source-derived baremetal/Sv39 coverage, not full historical Linux closure;
the original board error's trial/phase was not identified. No M6 result exists here.

## Worker And Failure Contract

Reuse the frozen M6 image and its Runner, plus the established checked-worker
factory from `ordered_reduction/original_remaining9_vcs_m6_plan01/replay.py`.
No common file is edited. Only this adapter's in-memory monitor wrapper extends
the raw fail veto and writes `child_outcome.unvalidated.json` immediately after
the actual simulator monitor returns, BEFORE the Runner's generic postchecks.
The record preserves numeric 17, 0 or negative signal exits regardless of later
trace/provenance/oracle errors. It is explicitly NOT architectural acceptance.
If command identity cannot be read, the numeric outcome is still recorded and
strict validation rejects it. An exception before the monitor returns cannot
honestly supply an unknown exit code; it sets abort and cannot pass.

The existing common worker uses sticky cancellation at the first failure.
Both raw logs veto contradictory PASS+FAIL. Exact membership, numeric exit,
command/ELF/image identity, full unchanged oracle, pre/post module/input pins,
and no late abort are required. No retry, coverage, FSDB or builds. Each group
records its observer command/output and final strict result. COMPLETE requires
all 24 groups; raw child success is never substituted for oracle acceptance.

## Bounds And Admission

Maximum four simulators; original 2400 seconds per simulator and 2700 seconds
per group INCLUDING oracle postcheck. Six waves give a 16200-second worker
envelope; reuse the old four-job 16800-second outer service bound, with 600
seconds for teardown. No automatically enlarged case timeout. Dispatch refuses
when a full original group envelope no longer fits. Old M2 observed per-group
simulation elapsed was 1345.25 to 1800.93 seconds; the ordered four-job estimate
is 9689.75 seconds (2.69 hours), not a measured M6 duration or guarantee.

Preparation records a service COMMAND TEMPLATE ONLY. Future worker must be the
direct MainPID in `ara-nf7-current96-m6-01.service`, RuntimeMaxSec=16800,
KillMode=control-group, Restart=no. Live+new4+unused reservations must be <=24
with >=32GiB available. Parent must reconcile reservations before consuming
this plan (default unused reservations zero); no repeated admission attempts.

Required fresh parent review JSON (not supplied by preparation):

```json
{
  "decision": "AUTHORIZE_NF7_CURRENT96_M6_ONCE",
  "plan_sha256": "PREPARED_PLAN_SHA",
  "unit": "ara-nf7-current96-m6-01.service",
  "image_sha256": "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0",
  "budget_risk_accepted": true,
  "nf2_gate": {
    "decision": "TERMINAL_INDEPENDENTLY_ACCEPTED",
    "terminal_path": "ABSOLUTE_NF2_REMAINING34_PREPARED01/complete.json",
    "terminal_sha256": "SHA",
    "plan_sha256": "SHA",
    "review_path": "ABSOLUTE_INDEPENDENT_REVIEW",
    "review_sha256": "SHA"
  }
}
```

NF2 path is fixed in `replay.py`; its whole-batch terminal, M6 image, pinned
independent review and new parent authorization are checked only at authorized
run, not while it is active. Parent review attests the independent review's
meaning; the worker binds its exact bytes. NF2 terminal is not a NF7 PASS.

Host tests use synthetic artifacts and existing immutable metadata only.
After Host PASS, `prepare` pins all local/transitive observer/worker modules,
source/ELF/oracle inputs and image. `dryrun` uses the frozen Runner's dry mode
for 24 command preparations only. Final readiness does not authorize launch.
