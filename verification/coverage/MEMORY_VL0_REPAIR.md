# Independent Segment-VL0 Repair Regression

Launched with user approval on 2026-09-28 in the sole signoff worktree.
Only new orchestration files are owned here; existing RTL, tests, checkers,
coverage adapters, and runner modules are not edited.

Output: `verification/out/vcs-memory-vl0-repair-20260928-01`.

Services:

- `ara-memory-vl0-repair-build-20260928-01.service`
- `ara-memory-vl0-repair-regression-20260928-01.service`

The build freezes dispatcher SHA256
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`.
It takes the compile command from
`verification/out/repair-closure-coverage-20260927-01/compile.command.json`,
changing only `buildpath` and `sim_dir`. Configuration remains default,
four lanes, VLEN=1024, QBS/AKV/AKV2, 2 MiB L2, no FSDB, and
line/condition/FSM/toggle/branch coverage. A fresh source manifest, build-image
inventory, configuration comparison, and normalized VCS-command comparison
must pass. No old image, verdict, or VDB is admitted.

The dependent regression service is already running, using the existing
bounded build-service wait API. It cannot run any test until this new build
has recorded PASS and source/image checks pass. No rebuild or retry occurs.

Execution order:

1. `vmemory_gap_nf5_e8_indexed` alone, with selfcheck and independent trace audit.
2. Remaining 39 memory-gap cases plus controls, using eight workers.
3. PASS-only DVE export, only if all 51 cases passed their existing audits.

Ten existing RVV controls: `vle8`, `vse8`, `vl1r`, `vs1r`,
`vsegment_emul_edges`, `vindexed_vstart_edges`, `vunit_vstart_edges`,
`vlseg`, `vsetvl`, and `vadd`. These cover old VL0 unit operations,
whole-register VL0 exclusions, segment vstart/EMUL, and ordinary execution.
AXPY uses the available frozen repair-closure ELF and the existing UVM audit
and <=2810-cycle regression gate. Every simulation has a 300-second budget;
audit and process-cleanup overhead have the existing runner's separate bounds.

The existing repair worker, directed runner, independent audits, and fail-fast
scheduler are reused. Any non-PASS stops dispatch and cleans up active workers.
Failed/cancelled evidence remains in place; DVE is not launched after a failure.
DVE inputs must be this new image's pristine design VDB and one audited PASS
VDB per selected case inside this output. Old473 coverage is never mixed in.
This is a 51-case repaired-image regression, not cumulative signoff coverage.

## Status

From the signoff worktree:

```sh
systemctl --user status ara-memory-vl0-repair-build-20260928-01.service ara-memory-vl0-repair-regression-20260928-01.service --no-pager
cat verification/out/vcs-memory-vl0-repair-20260928-01/status.json
```

Logs are `compile.log`, `build-service.log`, and `regression-service.log` under
the output directory. Case evidence appears in `outcomes/`, `results/`, and
`logs/`; scheduler state is in `focused-scheduler/status.json`, then
`scheduler/status.json`. Final coverage evidence is `collection.json` and
`dve/summary.csv` (plus waiver report when applicable).

Both services have `KillMode=control-group`, `Restart=no`, and
`RemainAfterExit=no`. Build/regression service bounds are 7500/15000 seconds.
Startup/progress was checked once for each service; leave the independent
background build running and inspect results after completion.
