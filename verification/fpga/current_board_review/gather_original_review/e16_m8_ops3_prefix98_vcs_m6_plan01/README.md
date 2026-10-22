# M6 e16/m8 vi31 Natural Prefix98 Runner

Prepare-only successor. No DUT, build, Spike rerun, service query or live
simulation inspection. All source/reference and previous runner files remain
sealed. This directory follows the ei16 runner contract, with the actual vi31
source, argument and oracle distinctions below.

## Source and Exact Scope

- Source READY: ../e16_m8_ops3_prefix98_prepare01/READY.json
  SHA a354337fd4e6f2177b572db9ae372d580558fc55c12b21c1c05e3eac3f1bc672.
- Independent source/reference REVIEW:
  ../e16_m8_ops3_prefix98_audit01/REVIEW.md
  SHA 7e198123638368bafea19c5160b9b88a8cbab55a4ccd67c416400e4ef5ba4fd2.
- Independent audit.json SHA
  f7a31b0d7c0420ca78fb979875d38834a0cb19f064f7e77c20b37751c7c4ee22.
- Exact SoC ELF SHA
  c1064255efa0ff19d492d263723d1c7b88ad9521983ae07d12ecf8a753b5cf44.

Keep98 calls/97 predecessors, cap512, original RNG/setup/order/scalar-slot0,
full50176 results +196 guards, all13 helper instructions and98 returned-vstart
checks. Endpoint [0,3,0,6,0,1] is VL512/start256. Original recovery177 identity
and unknown stopped tuple are unchanged. This is not full2688-child,
Linux execution, or an exact historical-stall claim.

The sealed source READY predates independent review and retains its PENDING
label. Preparation requires the separate exact ACCEPTED audit and review
hashes above; it does not rewrite that historical READY.

## vi31 Discriminants

Actual ELF target must be 308fbc57, vrgather.vi v24,v8,31,v0.t, unsigned
immediate31. Actual a6/t3 remain0; a1 must equal ordinary indices, not
indices16. Unused index load and mv are retained in the13-instruction sequence.

Active selected values are input[31]=32689, not input[0]=61881, literal0,
or input[indices16[i]]. Legal source range is cap512, not current VL.
Prestart, tail and inactive elements retain91. The checker uses the accepted
vi31 model and requires all514 unique scalar oracle loads each call, all setup
bytes, all13 actual instruction encodings/order, three vset returns, correct
arguments/target VL/start, returned-vstart0, original CTRL exit0 and a001 park.

Host fault injections assert their source coordinates before corruption:

| Call / element | Correct result | Negative |
| --- | --- | --- |
|18 /0, VL1/start0 |32689|vx scalar0 input61881, or literal0|
|98 /511, VL512/start256 |32689|signed-immediate/OOR zero|
|49 /2, VL3/start1 |32689|ei16 index511 input44879|
|33 /0, VL2/start1 |91|prestart overwritten32689|
|18 /1, VL1/start0 |91|tail overwritten32689|
|74 /255, VL256/start128 sparse mask |91|inactive overwritten32689|

Additional tests cover wrong generic and vx target encodings, indices16
pointer substitution, both guards, returned-vstart, setup/RNG/missing oracle,
exit/park, raw markers, image/ELF/plan/budget drift and cancellation.
These are Host checker fixtures, not fabricated source or DUT evidence.

## Runner Contract

Jobs1, case9000s, direct service10200s, seed1, +NO_FSDB, no UCLI/coverage,
private exact ELF, full raw CSV, first failure stops the private process group,
no retry. Runtime monitor includes explicit RVV_PERMUTE_DETAIL veto.
The actual frozen monitor is tested using a plain Python child emitting the
authentic partial DETAIL line with no newline/final FAIL; it must stop within5s.

Full generic trace and strict prefix validation are required, with COMPLETE,
exact PASS1 metadata, raw console and simulator-log oracle, zero exit, private
inputs/command identity and unchanged source/image/helper pins. Late abort or
pending signal cannot publish PASS. The new worker also rehashes and rereads
the on-disk plan after expensive validation to reject in-run plan drift.

Run must be the exact service MainPID/cgroup with RuntimeMaxSec10200,
KillMode control-group and Restart no. Trusted explicit UID bus environment
is used only on authorized run; Host service queries are mocked.
Outer service exit is not inferred from a worker PASS or collected defaults.

Cost1905086 retired /273/s =6978.34s; +20%=8374.00s fits9000, but is an
estimate, not guaranteed runtime. Bounds do not increase on failure.
Runtime admission checks cap24 and memory>=32GiB; reserved-slots denotes only
unused external reservations, not a duplicate of actual running processes.
Prepare records no live resource snapshot.

## Preparation and Admission

Host37 tests and preparation are the only operations authorized here:

```sh
python3 -B test_host.py
python3 -B replay.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
```

prepared01/plan.json binds accepted source/reference/review, Host results,
actual M6 image/configuration/source/executable and imported helpers.
prepared01/ready.json contains the pinned plan SHA and service command with
unresolved parent-review placeholders. Preparation does not create a service.

Independent runner review must precede parent admission. Future review:
```json
{
  "decision": "AUTHORIZE_E16_VI31_PREFIX98_ONCE",
  "plan_sha256": "EXACT_PLAN_SHA",
  "unit": "ara-gather-e16m8-vi31-prefix98-m6-01.service",
  "budget_risk_accepted": true,
  "reference_ready_sha256": "a354337fd4e6f2177b572db9ae372d580558fc55c12b21c1c05e3eac3f1bc672",
  "source_review_sha256": "7e198123638368bafea19c5160b9b88a8cbab55a4ccd67c416400e4ef5ba4fd2"
}
```

Run additionally requires --authorize-run, --plan-sha256 and pinned
--parent-review/--parent-review-sha256. No approval is manufactured here.
A missing or mismatched authorization cannot reach service/resource admission.
