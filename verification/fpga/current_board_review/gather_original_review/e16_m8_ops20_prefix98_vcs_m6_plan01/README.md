# M6 e16/m8 ei16 Natural Prefix98 Runner

Prepare-only successor after independent source/reference ACCEPTED. No DUT,
build, Spike rerun or live-simulator query. Original references and all sealed
helpers remain unchanged. Strict retirement checking derives from the e16
plan02 contract; service/abort/plan-drift/raw-monitor protection follows the e8
successor contract. No generic replacement program or vx oracle is used.

## Pinned Authentic Scope

| Input | SHA256 |
| --- | --- |
| `../e16_m8_ops20_prefix98_prepare01/READY.json` | `1fde3acbc776a3ce8b5ea40d20bfb4e46827758cacfacf5e0333c3d6d4526149` |
| Independent `../e16_m8_ops20_prefix98_audit01/REVIEW.md` | `c1cc53ccf3848c8af2bb6004ea02517f00eb358eaebb6e6a6da49e5d27dbeb67` |
| Independent `audit.json` | `5fd1d2e3add1f801d1d8f3ad9cd708848b41f445080ff63629231cc49897ae79` |
| Original SoC input ELF | `c4d681ad58bf1e46e121ffc3c3652cabc1b2a62100fc3987012c502e53fc89fd` |

The independent audit must have exact accepted status, READY identity,
retirement count and13x98 helper counts before preparation. Both review and
machine audit are hashed, not inferred from file existence. Image manifest,
snapshot/source/configuration, executable and runtime dependencies are checked
through the established M6 `image_context` and pinned without rebuilding.

Scope is first98 original child calls, all97 predecessors, cap512, seed0/scalar
slot0, original RNG/input/index/predicate/output initialization, all13 assembly
instructions and returned-vstart. Endpoint `[0,20,0,6,0,1]` is VL512/start256.
Every call retains512 result reads and two guards:50176 results +196 guards,
50372 unique actual LHU loads total. Actual three vset returns/call, target
VL/start/scalar argument, CTRL exit0 and original `a001` park are required.

This is not the full2688-call child, original Linux replay, exact historical
stalled tuple (still null), or acceptance of other stall records. Prior DUT
acceptance is not transferred to this new source ELF.

## EI16-Specific Strict Gate

- Actual a1 must equal the ELF's `indices16` symbol, not `indices`, even though
  the arrays have identical16-bit values at this SEW.
- Actual target must be `38880c57`, `vrgatherei16.vv v24,v8,v16,v0.t`, at the
  actual linked PC. All13 instructions must match archived helper encodings.
- Expected active result is `input[indices16[i]]` for index<512, otherwise0;
  source indices beyond VL remain legal. Prestart, inactive and tail retain91.
- Both index arrays and all other setup bytes must have actual initialized
  values; missing bytes are rejected. No constant scalar-source substitution.
- Generic frozen trace checks retirement/CVX/uop structure; strict CSV checks
  original calls/setup/values/CSR/order. Both raw logs require exact full98
  oracle markers and exit0, with raw failure veto even after PASS.

Host distinction points use the original model and are asserted before fault
injection. Checker indices below include the leading guard:

| Genuine call / element | Index and expected value | Injected error |
| --- | --- | --- |
|49 /2, VL3/start1 | index511 ->44879, despite index>=VL | vx0 value61881 |
|66 /255, VL256/start128 | terminal index512 ->0 | in-range source61881 |
|98 /511, VL512/start256 | terminal index1 ->538 | dropped-data zero |
|74 /255, sparse predicate | inactive index512 retains91 | unconditional OOR zero |

These are checker tests, not measurements of RTL end-token/FIFO behavior.

## Fixed Bounds and Ownership

Jobs1, case9000s, direct service10200s (2h50min), seed1, `+NO_FSDB`, full raw
CSV/private ELF, no coverage or UCLI, no automatic retry. First raw failure
stops the private process group and latches abort. COMPLETE/PASS1, exact
summary/inputs/command/image, elapsed<=9000 and unchanged pins are required
before signal-blocked final publication. Abort during expensive validation
or a pending signal cannot publish PASS.

The worker must be the actual service MainPID in its exact cgroup, with
`RuntimeMaxSec=10200`, `KillMode=control-group`, `Restart=no`. Trusted explicit
UID bus environment avoids sanitized-environment false failures. No service
exit is inferred from worker status or collected-unit defaults.

Reference2134409 retired gives7818.35s at273 retired/s,9382.02s with20% margin.
The latter exceeds9000s but is below3h. Fixed budgets are not increased and no
guaranteed completion is claimed. Prior M5 rates683..687 imply3107..3125s,
but are not this case's measured VCS throughput.

Static prepare records no resource snapshot and does not inspect live DUTs.
Authorized run checks cap24, available memory>=32GiB, jobs1 and unused external
reservations counted once. A new parent plan-SHA approval must explicitly
accept budget risk; source/reference acceptance alone cannot launch.

## Commands and Parent Gate

```sh
python3 -B test_host.py
python3 -B replay.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
```

`prepared01/plan.json` pins source/reference/independent review, helpers, Host
gates and actual M6 image/configuration. `ready.json` contains plan SHA and a
service command with intentionally unresolved parent-review placeholders.
No approval or service is created by preparation. Future parent review JSON:

```json
{
  "decision": "AUTHORIZE_E16_EI16_PREFIX98_ONCE",
  "plan_sha256": "EXACT_PLAN_SHA",
  "unit": "ara-gather-e16m8-ei16-prefix98-m6-01.service",
  "budget_risk_accepted": true,
  "reference_ready_sha256": "1fde3acbc776a3ce8b5ea40d20bfb4e46827758cacfacf5e0333c3d6d4526149",
  "source_review_sha256": "c1cc53ccf3848c8af2bb6004ea02517f00eb358eaebb6e6a6da49e5d27dbeb67"
}
```

Actual run additionally requires `--authorize-run`, exact `--plan-sha256`, and
`--parent-review PATH --parent-review-sha256 SHA`. The pinned review and inputs
are rechecked at completion. A wrong/missing review cannot reach admission or
simulator launch. Independent runner review precedes parent admission.

## Host Tests

The32 tests use synthetic protocol fixtures derived from actual ELF symbols
and the accepted original model, never synthetic source acceptance. They cover
full98/generic consistency, setup/RNG/argument/encoding/data/guard/vstart,
EI16 distinctions above, missing oracle/truncation/exit/park, strict markers,
ELF/image/plan/budget drift, parent approval, cancellation/COMPLETE/pending
signals, capacity math and mocked sanitized-service queries.

The retained authentic `RVV_PERMUTE_DETAIL op=20` first-error line is also
tested through the **actual frozen runner monitor** with a plain Python child
that writes a partial line and sleeps. The test requires fail-stop within5s
without newline/final FAIL, plus checked-runner sticky abort. No simv is run.
All resource/service tests use synthetic inputs/mocked queries, not live jobs.
