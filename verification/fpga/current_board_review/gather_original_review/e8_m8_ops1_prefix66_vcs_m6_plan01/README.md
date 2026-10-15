# M6 e8/m8/op1 Natural Prefix66 Runner

Preparation only. No DUT/build/Spike execution or live-simulator query is
performed by preparation. The exact existing M6 image and original software
ELF are reused. No e16 runner, shared helper, accepted reference or sealed
output is changed. The reference's earlier failed audit01 remains failed;
accepted audit02 and the independent review are used without rerunning Spike.

## Exact Scope

- Accepted reference: `../e8_m8_ops1_prefix66_prepare01/READY.json`, SHA256
  `d05ff6b45d69a05b41d3558aa5e8d148cfd085b6f17f017a5b81b6cf78006af3`.
- Independent source/reference review:
  `../e8_m8_ops1_prefix66_audit01/REVIEW.md`, SHA256
  `86c3a6291a4e3011e931eb3734becaab47a795a033a1ca67e12078c01f59b346`.
- Identical SoC ELF SHA256:
  `791d817193c9b46eec48e6feee8b1d9c8ecf289b588253b21c1f59a54314d2c6`.
- All66 original calls, all65 predecessors, cap1024, original RNG/setup and
  helper13 instructions retained. Endpoint `[0,1,0,4,0,1]`, VL512/start256.
- Mandatory67584 scalar results,132 guards,66 returned-vstart checks and
  three actual vset returns per call. Each call verifies4226 initialized
  values, including byte data/indices and original16-bit `indices16`.
- The strict CSV gate checks actual ELF-derived PCs, encoding/order/arguments,
  LBU output/guard positions, CTRL exit0 and original `a001` park. Generic
  frozen trace validation separately checks retirement/CVX/uop contracts.
- Both raw logs require exact PREFIX66/case/simulator success markers. Explicit
  `RVV_PERMUTE_DETAIL` veto catches the authentic first-error partial line,
  before newline or final FAIL. Errors after PASS also veto acceptance.

This is not the full2688-call child, original Linux replay, exact historical
stalled tuple (still unknown), or acceptance of other stall records.

## Fixed Budget and Launch Hold

Jobs1, case9000s, direct service10200s (2h50min), no retries, no timeout
adaptation, no waveform on initial run. Full commit CSV and private ELF are
mandatory. The service uses `KillMode=control-group`, `Restart=no`; the worker
must be its actual MainPID in the exact cgroup. Trusted explicit UID bus
environment is retained. Sticky abort survives expensive validation and the
signal-blocked final publication decision.

Reference retirement is2745395. At273 retired/s, nominal10056.39s exceeds the
9000s case budget; plus20% is12067.67s, exceeding3h. No guarantee of completion
is claimed. Keeping9000s requires305.04 retired/s without margin, or366.05
with20% time margin. Accepted M5 cap512 prefixes measured683.20..686.93
retired/s, but do not establish M6 cap1024 throughput. The budget is unchanged.

Actual launch requires all three gates:

1. E16 prefix98 **terminal acceptance**, not progress: pinned complete PASS,
   no abort, unchanged pins, exact same M6 image, PASS/rc0/budget, COMPLETE1,
   pinned raw logs/CSV/input/command and full strict98 oracle evidence.
2. A **new parent review**, explicitly pinning this plan and the e16 independent
   acceptance document, and accepting this fixed-budget risk.
3. Fresh runtime resource admission: cap24, MemAvailable>=32GiB, jobs1;
   external unused reservations count once. Preparation records resources as
   deferred and does not inspect any live simulation or service.

Terminal e16 evidence is read only by authorized `run`, never by `prepare` or
real-data Host tests. Service-exit provenance remains separate; no GC/default
service state is fabricated. This preparation does not authorize launch.

## Commands and Approval Contract

Host-only test command:

```sh
python3 -B test_host.py
```

Static preparation command (no compiler/simulator/process scan):

```sh
python3 -B replay.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
```

`prepared01/plan.json` binds reference, source, ELF, image/snapshot/config,
frozen runner, transitive helpers, host gates and reused e16 top-level scripts.
`ready.json` records its SHA and a **non-launchable placeholder** service command.
No parent approval file is generated. At authorized launch, the parent supplies
`--parent-review PATH --parent-review-sha256 SHA` with this JSON contract:

```json
{
  "decision": "AUTHORIZE_E8_PREFIX66_ONCE",
  "plan_sha256": "EXACT_NEW_PLAN_SHA",
  "unit": "ara-gather-e8m8-prefix66-m6-01.service",
  "budget_risk_accepted": true,
  "e16_terminal_accepted": true,
  "e16_complete": {"path": "/absolute/terminal/complete.json", "sha256": "SHA"},
  "e16_independent_acceptance": {"path": "/absolute/acceptance/document", "sha256": "SHA"}
}
```

Neither the parent's acceptance flag alone nor an unpinned runner PASS is
sufficient: the worker validates the referenced terminal/raw-evidence contract
before service/resource admission. Approval and dependency evidence are rehashed
after the run as well. No source/ELF/oracle rebuilding occurs.

## Host Verification

`test_host.py` derives synthetic protocol fixtures from this actual ELF's
symbols and original reference model. These fixtures test the checker, not DUT
behavior. The27 tests cover full66/generic trace agreement, missing setup/RNG,
wrong arguments/encoding/output/guard/vstart, missing oracle/truncation,
exit/park, exact markers/raw veto, ELF/image/plan drift, missing/invalid e16
acceptance or parent review, sticky abort, validation exceptions, COMPLETE,
pending signals, capacity arithmetic and sanitized user-bus handling.

The actual retained Host first-error line (expected185/actual184) also runs
through the **real frozen runner monitor** using a plain Python child that
prints a partial line and sleeps. The test requires prompt fail-stop and abort
latching without final FAIL. It never executes simv. Resource/service tests use
synthetic inputs or mocked queries; no live-DUT status is queried.
