# Negative Stride Single: M6 Prepare Only

One unchanged source-derived SoC ELF for the archived
`rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3`.
Runtime ID is `negative_stride_load_e16_m1_u1_s0_b3_m2_f0_g3`; these names are
deliberately separate. This is one real Sv39 single, not Linux signal-frame
equivalence, the96-case parent, or current DUT acceptance.

## Fixed Inputs And Scope

- Reference READY SHA `d20a279ff09bbad626141a386a12160634b0ad36ca82ff6da661c1c7ddcc4d52`.
  All64 original pins are retained without edits, including actual raw reference.
- SoC ELF SHA `04e25a1fa3b6ba094af6d60d50f8ec0dd60f2ec2503f47dda05fd2011c5a0a43`.
  No compile, new reference, RTL edit, image build or FSDB.
- Existing M6 image `/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`;
  image.json SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
  Snapshot/source/configuration/image/import pins are checked before and after.
- Confucius `negative_stride_load_adapter_review01/decision01.json` is bound
  under its actual `APPROVED_SEALED_ADAPTER_STATIC_REVIEW_ONLY` schema. Its
  REVIEW SHA is99fabe9cf0ee0dd3dad424ee8eedc93b0646d4fcc2f3c1fb11ac6514842e71f7.
  This is not independent raw-reference recomputation or launch permission.

## Checkers

Frozen runtime/runner/framework are imported read-only. The new strict RVFI
observer checks every retired PC/encoding against the actual SoC ELF, the
original capacity and ten-instruction helper window, unused store-helper
rejection, fault interruption, unchanged-PC retry and actual MRET GPR/CSR
context. Spike's faulting partial target record is not required as an extra
successful RVFI retirement. Original load helper enters once; retry does not
reload destination or change baseP+22/stride-8/start5.

Scalar store addresses/BE/source values and scalar load addresses/BE/signed
results are checked. Vector destination bytes are invalidated at their actual
store instruction and reconstructed only from subsequent actual scalar loads.
Four full byte-oracle checkpoints include initial and final8KiB, all page-table
neighbors, original input/offset/mask arrays, snapshots and results. The exact
4096 halfword read sequence is required at each memory checkpoint. Final64
results, guards output0/65, extra physical-storage checks and all17274 original
plus adapter scalar comparisons remain required. Lower2048 refill is observed
in address/value/order; prefixP+6 poison and final unpoisoned result are checked.
The extra full fault snapshot is a strengthened adapter safeguard, not an
expanded claim about the original historical oracle.

The existing generic trace validator independently checks CVX ownership and
responses, architectural request order, backend VID allocation/done matching
and fully drained terminal state. Exactly one CVX load exception is required.
Completion needs actual scalar CTRL write0 and only original a001 parking
afterwards; Spike HTIF1 is not an interchangeable successful VCS exit.

Two durable outcome files precede postcheck acceptance:
`monitor_outcome.unvalidated.json` records actual numeric monitored wait result,
timeout/failure/abort and command identity before even the parent runner's
trace validation; `child_outcome.unvalidated.json` records its returned result
before case-specific artifact checks. Both use exclusive creation and fsync.
Neither outcome by itself is architectural acceptance. Raw failures, absent
oracle, input drift, interruption and postcheck exceptions cannot yield PASS.

## Host Evidence

`csv_host03/status.json`: full positive213516 synthetic rows using actual SoC
PC/code/symbols and full independent oracle; ten discriminating wrong-data,
inactive/tail/guard, retry, missing-checkpoint/guard/CTRL negatives rejected.
Synthetic events are Host checker tests, never DUT evidence.

`host02.json`: ten worker tests PASS, covering runtime/history mapping,
seed/preload/cwd errors, missing oracle/ELF drift, checker-throw durable outcome,
actual partial-line failure monitor, numeric timeout persistence, late abort,
budget/original64/disk-plan drift, denied unauthorised run and generic protocol
missing response/arch/uop completion. The monitor Host test runs only a tiny
Python child that prints a partial failure and sleeps, not a simulator.

Preserved preparation failures: csv_host01/02 were synthetic setter omissions
(s11 selection and t1); host01 was a missing Host import path. None involved
DUT/reference execution or relaxed source/oracle checks. Only successor results
are used as prepare gates; old failed artifacts remain intact.

## Budget And Ownership

Fixed jobs1, simulation3600 seconds, direct worker/service4800 seconds. No
automatic retry or extension. Actual reference836971 firmware records scales
to about22.5min at the measured NF2pilot4 ~743/s plus20%; a slow273/s plus20%
proxy is3679s, slightly above3600. This risk is explicit, not a reason to expand
the authorized bound or shrink the oracle. Timeout means incomplete acceptance,
not an established RTL bug without progress/cycle evidence.

Launch checks the real user-manager unit, current worker MainPID and exact
cgroup, loaded/active/running state, RuntimeMaxSec4800, KillModecontrol-group
and Restartno. Trusted UID user-bus environment is explicit. Runtime resources
must satisfy live+new+unused-reservations <=24 and MemAvailable>=32GiB. Both
comm and argv0 detect simv; existing live workers are counted once. Prepare and
dryrun do not query live services or simulations. Use reserved-slots only for
unused reservations, never duplicate live workers.

## Commands And Launch Gate

From this owned directory, preparation uses:

```sh
python3 -B replay.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
python3 -B replay.py dryrun --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --plan-sha256 PLAN_SHA
```

The exact resolved future command and systemd invocation are emitted into
`prepared01/ready.json`. They are **not executed by prepare/dryrun**. Main must
supply a newly pinned parent review with decision
`AUTHORIZE_NEGATIVE_STRIDE_SINGLE_M6_ONCE`, exact plan SHA/unit/READY,
`adapter_review_pins` equal to the plan and `budget_risk_accepted=true`, then
explicitly invoke `run --authorize-run --parent-review ...
--parent-review-sha256 ...`. The worker must itself be the direct service owner.
Fresh private ELF/work/log/CSV outputs live only under prepared01/replay.
First failure stops this one job and preserves all artifacts; no shared or
sealed input is changed. Source-single results cannot be counted as parent96.
