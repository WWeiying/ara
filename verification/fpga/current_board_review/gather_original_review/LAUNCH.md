# Candidate03 Eight-Single Launch

User-authorized one-shot replay. No source/ELF/oracle/RTL/image changes,
image build, automatic retry, coverage or waveform capture. The preparation
and source selection remain in `SELECTION.md`.

## Command And Ownership

Executed from `/home/wangwy/openproject/ara_dsa_signoff_integration`:

```sh
python3 -B verification/fpga/current_board_review/gather_original_review/replay_candidate03.py --launch
```

Do not rerun that launch: the fixed output directory and unit reject collisions.
`vcs_candidate03_01/service_command.json` records the exact `systemd-run`
argv. The directly owned worker is MainPID7929 in
`ara-gather-original8-candidate03.service`, `Restart=no`,
`KillMode=control-group`, outer maximum1800s.

The worker calls the unchanged `integration/run.py:run_programs`, with its
ordinary frozen-framework runner and a batch-local resource/failed-marker
wrapper. Exact logical runner argv is `vcs_candidate03_01/plan.json`'s
`runner_command`: `run --image /home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image`
with `--programs .../gather_original_review/soc01`, independent
`--out .../gather_original_review/vcs_candidate03_01/replay`, jobs2,
timeout300, execute, and all eight explicit `--case` names. No build path is
called. A FAIL retains evidence and follows the existing runner's cancellation
policy; there is no retry or repair.

## Admission And Actual Progress

`resource_gate.json`: two external NF7 simv, no active Tesla comparison
simv/worker, MemAvailable183.897GiB. NF7 reserve2 is already occupied and is
not counted twice. Own2 + unoccupied Tesla2 + mask-alias1 + external2 gives
**7 <= cap24**, with MemAvailable>=32GiB. Each case has a new recorded gate
under `admission/`; all job output is isolated from Tesla's directories.

`actual_simv_confirmation.json`: two bounded samples, three seconds apart.
Both executable paths are the exact candidate03 simv; cgroups match the
owned systemd service; CPU time, CSV bytes and commit cycles advance:

| PID / Initial Case | Commit Cycles | CSV Bytes |
|---|---|---|
| 8107 / gather_e16_m1_ops0 | 33071 -> 36131 | 2318336 -> 2547712 |
| 8112 / gather_e8_mf8 | 35463 -> 38729 | 2658304 -> 2916352 |

This is startup/progress confirmation, **not terminal acceptance**.
Completion polling stopped after these samples.

## Outputs And Automatic Acceptance

All outputs: `verification/fpga/current_board_review/gather_original_review/vcs_candidate03_01/`.
`service.log` and `runner.log` retain worker/runner diagnostics. Per-case
`replay/tests/<name>/` retains console, VCS log, private ELF/input provenance,
command and full commit CSV. `worker_exit.json` records the runner outcome.

The worker automatically invokes separate `check_terminal.py` after the
runner ends. `complete.json` is authoritative only when its status is
`PASS_8_ORIGINAL_SINGLES_CANDIDATE03`: exact eight membership/counts,
COMPLETE runner, original cases1/errors0 oracle, unambiguous begin/pass/end
markers, Core success/tohost0, every exit0, failed-marker veto in both logs,
staged ELF/image identity, independently revalidated complete trace with no
vector exceptions, and all pins unchanged. Otherwise it writes NOT_ACCEPTED
with retained failures/cancellations; cancelled cases never count as PASS.
`checker.log` contains checker stdout. Two host checker tests cover false
PASS, failure tokens and wrong/missing/duplicate markers; three source tests
also passed before admission. No checker or sealed worker edit after launch.
