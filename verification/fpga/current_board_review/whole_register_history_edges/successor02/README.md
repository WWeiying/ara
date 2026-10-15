# Whole59 Actual Worker Successor

New code/output only; `../launch_plan01` and `../prepared02` are sealed inputs.
No RTL, fixture, oracle, ELF, existing helper, or image changes. Host preparation
replays existing59 Spike logs, not new Spike or DUT execution. Each real run
will use the exact accepted SoC ELF with the unchanged integration runner.

`csv_adapter.py` incrementally checks actual RVFI scalar addresses/masks/data,
exact instruction words, both original1024-byte input and1088-byte destination
initializations, original arguments, predecessor/target order, inherited vtype,
two vstart readbacks per call, returned status, full1088-byte ordered output
values/guards per call, both target instructions, four preloads/two stores,
original cases/skips/errors counters and zero raw/CTRL exit. No oracle sampling.
Source and exact59 geometry remain bound to the sealed predecessor plan.

`driver.py` uses existing `integration/run.py`, accepted inotify live CSV reader,
and owned-process cancellation helper. A small six-way dispatcher adds strict
pair/aggregate acceptance. Pair deadline covers checker finish/publication;
timer and acceptance share the abort lock. All timers are joined before terminal
publication; pending signals, abort reason, incomplete membership, source drift
and campaign deadline veto PASS. Terminal files use owned atomic publication,
never the sealed helpers' exclusive save for rewriting an existing result.

Limits unchanged: jobs6, simulator600s/pair, pair660s including checking,
campaign3000s, service3600s. Original59 are independent fresh pairs, not full1134
continuous history or original Linux execution. One failure stops new dispatch
and cancels owned peers, with no automatic retry. No other jobs are controlled.

## Prepare Only

```
python3 -B host_check.py
python3 -B driver.py prepare --out "$PWD/preflight01"
```

The prepared `programs/programs.json` binds unchanged59 ELFs. Its new
`bindings/provenance.json` only points to their actual pre-existing sources;
it neither recompiles nor substitutes the sources. Dryrun has no `--execute`.
Host negatives cover altered output prefix/body/end/guard, inherited vtype,
target, vstart, skip counter, truncation and exit, plus focused real-filesystem
timeout/cancel publication tests. These are not DUT PASS.

## Parent Terminal Gate

After Tesla's independent terminal audit, parent creates a NEW strict-acceptance
record (or equivalent new record referring to that audit) with this schema:

```json
{
  "status": "WHOLE1134_STRICT_TERMINAL_PASS",
  "output": "/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/whole_register_original/vcs_candidate04_01",
  "image_sha256": "e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673",
  "plan_sha256": "ACTUAL_WHOLE1134_PLAN_SHA256",
  "groups": 20, "cases": 1134, "skips": 366,
  "firstfailure": null, "pins_unchanged": true,
  "service": {"unit": "ara-whole1134-candidate04-01.service", "Result": "success", "ExecMainStatus": 0, "MainPID": 0},
  "evidence_pins": {"ABSOLUTE_EVIDENCE_PATH": "SHA256"}
}
```

`evidence_pins` must bind the actual independent audit, old plan/complete,
replay run/summary, and every20 partition's private ELF, inputs, simulator
command, console and full CSV. Worker rechecks old membership/return codes,
strict elapsed bounds, original pins, no firstfailure, and no residual old-owned
process. GC is accepted only with pinned historical terminal evidence, never
missing-unit default success. This gate executes only in authorized worker,
not preparation. Parent attestation of strict audit must not be fabricated.

Use `preflight01/review.template.json` to create a NEW `review.json`, binding
that acceptance by path/hash and setting `parent_authorized=true`. Populate
`reserved_units` with parent's current exact unit/slots roster, excluding the
finished whole1134 reservation. Capacity admission counts all actual simvs plus
unused reservations plus these6, <=24 and >=32GiB available. It performs one
snapshot, never waits/retries. Slots replace oldwhole6, not an additional6.

## Launch After Parent Review Only

From this directory, once review.json is supplied and parent explicitly triggers:

```sh
systemd-run --user --unit=ara-whole-history59-candidate04-01.service \
  --property=RuntimeMaxSec=3600 --property=KillMode=control-group \
  --property=Restart=no --property=WorkingDirectory="$PWD" \
  --property=StandardOutput="append:$PWD/preflight01/service.log" \
  --property=StandardError="append:$PWD/preflight01/service.log" \
  /usr/bin/python3 -B "$PWD/driver.py" worker --out "$PWD/preflight01" \
  --review "$PWD/preflight01/review.json" --authorize-run
```

Parent confirms actual simv and one short trace-growth observation once, then
does not poll. Final results are `preflight01/complete.json` and
`preflight01/pairs/pairNN/{complete,firstfailure}.json`; full runner evidence is
under each pair's `run/tests/whole_edgeNN/`. Independent terminal audit must
confirm service success in addition to worker PASS. No current launch permission.
