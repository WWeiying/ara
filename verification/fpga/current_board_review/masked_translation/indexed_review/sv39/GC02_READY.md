# NF7 GC Gate Successor Ready, Not Launched

## Diagnosis

The parent observed the original service exit 1 during preflight (25.33 s),
before `vcs_plan01/worker.json` or any VCS launch. Its read-only gate evaluation
identified `vcs_adapter.py:169`: `LoadState == loaded` rejects a successful
transient NF2 unit after systemd garbage collection. This is an orchestration
refusal, not an NF7 DUT failure. The original service journal was unavailable;
do not imply a recovered original traceback. Plan01 and all sealed inputs are
preserved without edits.

## Successor Contract

- New code: `successor_gate02.py`; host tests: `test_gate02.py`.
- New output: `vcs_plan02/`; no service or simulator was started by preparation.
- Plan SHA256: `86b5757f4be671cd4cb5227491b9a181b785566075cfc2d097543bf52e13edd4`.
- Predecessor SHA256: `fcad03c47c6bcb391c090b448289f8e6a6b65285177f6ab1e4fd9c2e8ed85d14`.
- Same accepted 24 ELF files, all 96 trials, byte-identical comparison ledgers,
  original scalar oracle, firstfailure checker, and fail-fast scheduler.
- Same candidate02 image: `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
- Same limits: four workers, each runner 2400 s, group orchestration 2700 s,
  outer service 16800 s. No rebuild or RTL/fixture change.

`gate02_host_tests.json` records 35 rejected negative controls, including GC
missing/FAIL/changed-identity evidence, missing raw CSV, live/residual NF2,
unknown active units, alien simv, false cgroup substring membership, wrong
arithmetic owner/image/run path, and more than four existing simvs. Positive
controls cover both units GC-terminal PASS and GC NF2 with four live arithmetic
simvs. These are host orchestration tests, not DUT evidence. All 24 dry runs
passed in `vcs_plan02/dryrun/summary.json`.

NF2 admission always requires its pinned full four-case completion, 4133-check
CSV analysis and matching analysis hash, raw CSV, COMPLETE run and full PASS
summary, accepted ELF, input image file map, and prior preflight pins. A missing
unit is accepted only with inactive/MainPID0/empty cgroup state and no NF2-owned
process, including non-simv workers. Ownership checks use exact cgroup components,
argv paths, and cwd; zombies do not consume live capacity.

Live arithmetic admission requires the exact reviewed service/main process,
plan02 argv, actual simv image path and run cwd, exact cgroup membership, at most
four arithmetic simvs, and at most eight arithmetic-plus-NF7 reserved slots.
An unknown active unit is always rejected. If arithmetic has become terminal
(including GC), a missing `complete.json` is not success: require all 38 PASS,
matching plan/image, COMPLETE run, exact case/ELF membership, and raw CSV/input
artifacts. Those terminal artifacts are hash-pinned before admission in
`worker.json.gate.terminal_pins` and rechecked after execution. This permits
completion between preparation and launch without reading/polling an in-flight
arithmetic summary during preparation. Any remaining arithmetic owner or any
other simv rejects terminal admission.

Admission performs one process snapshot after evidence hashing, not a waiting
loop. Parent scheduling remains responsible for not launching unrelated new
simulations concurrently with admission. Refusal writes a new local
`gate_refusal_*.json`; persistent stdout/stderr are mandatory below.

## Ready Command, Parent Review Required

The following command has NOT been executed:

```bash
H=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/masked_translation/indexed_review/sv39
systemd-run --user --unit=ara-indexed-nf7-candidate02-02 \
  --property=RuntimeMaxSec=16800 --property=TimeoutStopSec=60 \
  --property=KillMode=control-group \
  --property="StandardOutput=append:$H/vcs_plan02/service.log" \
  --property="StandardError=append:$H/vcs_plan02/service.log" \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B "$H/successor_gate02.py" worker --authorize-run --jobs 4 \
  --approved-plan-sha256 86b5757f4be671cd4cb5227491b9a181b785566075cfc2d097543bf52e13edd4
```

Future terminal evidence: `vcs_plan02/complete.json`; per-group evidence under
`vcs_plan02/groups/gNN/`. A launch refusal, service interruption, checker first
failure, and DUT first failure must remain distinct. No automatic rerun or
timeout increase. After authorized launch, confirm actual simv progress once,
then wait for a terminal notification without polling.
