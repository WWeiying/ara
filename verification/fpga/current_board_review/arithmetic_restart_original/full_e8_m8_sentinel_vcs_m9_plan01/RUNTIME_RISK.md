# e8/m8 Runtime Gate: HOLD

Decision: HOLD_RUNTIME_GATE_NO_DUT_AUTHORIZATION. Reference is independently accepted; that does not establish the unchanged10800s DUT budget. No executable worker plan or launch authorization is produced by this ledger.

## Actual Evidence

- Old monitor:255 / timed_out=true / 10800.112584s. Closed CSV diagnostic verifies2601 full source calls,1494 remain; no terminal simulator-cycle record exists. Original NOT_PASS and NOT_ACCEPTED are preserved.
- Closed prefix:1793564 retirements / cycle21859382. Existing seed0 same-tuple checkpoints imply12726678 additional cycles,17088.0 total wall seconds (~4.75h) using the crude recorded-cycle/wall ratio. This is a sensitivity proxy, not a bound or proof of progress throughout timeout.
- Exact same-boundary firmware-to-HTIF: old2825052 vs new2559063 (9.415% reduction). Scaling the above proxy by that ratio gives15479.1s (~4.30h), still above10800. This is not an M9 prediction or guarantee.
- The illustrative proxy needs36.80% total improvement to reach10800s, substantially beyond the measured firmware reduction.

## Loads, Stores and Remaining Cost

- Actual old comparator:1126125 scalar loads (275 per call); new:707445 including all IDs/gold/output/literal/stack loads.418680 dictionary LDs disappear,37.18% of comparator loads; output528255 reads remain. New lowering has0 comparator literal/stack loads but209340 constant-materialization instructions. Comparator instructions decrease160773, not418680.
- Actual new main has60249 scalar loads and584467 stores. No old whole-main load/store count is invented here. Mask128B/16SD each of1575 groups is unchanged in footprint; the loop/control code is what changed.
- All20475 helper memory operations remain. In particular02060c27 still stores the full1024B output group on all4095 calls after full-capacity vset, independent of the active target VL. a/b1024B inputs, fresh1026B output and full128B masks remain unchanged. Those costs cannot be removed by specializing scalar gold reads.
- Closed metadata records the same late output-store owner taking6156 cycles. Matched checkpoint intervals for the first five retained samples follow; these are observations, not a universal per-call lower bound.
  call2601: store6156 / checkpoint8620 cycles (71.4%).
  call2600: store6156 / checkpoint8849 cycles (69.6%).
  call2599: store6156 / checkpoint8840 cycles (69.6%).
  call2598: store6156 / checkpoint8602 cycles (71.6%).
  call2597: store6156 / checkpoint8602 cycles (71.6%).

- Under an intentionally simplified model where only comparator-load time improves, about99.0% of total old time would need to be that component. This is not a proof: other scalar savings, per-load latency, host/system load, vector/cache scheduling and possible old silent suffix are unknown. It nevertheless gives no sound <=3h admission basis.

## Watchdog Candidate and Safe State

Exactly+COMMIT_WATCHDOG=1000000 can improve observation, not reduce the workload or extend budgets. Progress means retire/accepted req-resp/backend alloc-done; arch_start alone is not progress. fflush is not fsync. Repeated scalar progress may hide an individual stuck owner; per-owner checks remain mandatory. Fixed local memory service is not a formal arbitration/translation gap bound. Per-progress fflush has unmeasured wall cost. The old6352-cycle observed event gap is not an exhaustive maximum.

Current safe action is HOLD before DUT admission. Do not shrink4095, retry the old run, change timeouts/flags/RTL, or infer a hardware deadlock from the timeout. Any worker source preparation remains non-executing and must carry this explicit runtime HOLD into Hilbert review. A future run needs new credible wall-cost evidence or separate explicit parent runtime-risk admission; neither exists here.

This calculation only reads sealed small JSON/Markdown and source sequence metadata. It does not stat/read/hash/parse raw, run Host/reference/compiler/simulator, or inspect any active task. Input paths and hashes are in runtime_basis.json.
