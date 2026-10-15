# Independent M6 ei16 Prefix98 Runner Review

2026-10-11. **PREPARATION_REVIEW_ACCEPTED; no blocking finding for the reviewed
sealed plan. Not launch authorization or DUT PASS.** Parent approval, budget-risk
acceptance and one actual runtime resource admission remain mandatory.

Reviewed directory: `../e16_m8_ops20_prefix98_vcs_m6_plan01/`.
No runner/test script execution, Host/Spike rerun, build, DUT, live-process/service query,
or sealed-file modification. This review read scripts, stored Host32 evidence,
plan/ready/source manifests and actual pinned file bytes. Only this new audit
directory was written.

## Findings and Conditions

1. **Budget risk, explicit and unchanged:** case9000s, service10200s, jobs1.
   Actual reference2134409 retired gives7818.35s at273 retired/s;
   with20% margin it is9382.02s,382.02s above the case budget. Parent must
   explicitly accept that risk; this is not a completion guarantee and does
   not authorize extending either bound. The outer service leaves1200s beyond
   the inner case bound for startup, teardown and expensive terminal checking,
   but that is not a measured worst-case bound for these activities.
2. **Nonblocking terminal plan-file hardening gap:** `replay.py:191` checks the
   on-disk plan SHA once before reading/using it. At `:221`, `validate(plan,
   image)` rechecks the retained in-memory plan and all786 pinned inputs, not
   `sha(out/'plan.json')` again. The plan itself is not in its own pins, nor in
   the final evidence map at `:224`. This does not change the authorized
   in-memory testcase or let changed source/ELF/image pins pass, but concurrent
   on-disk plan edits would not themselves prevent PASS publication. Keep the
   plan immutable and include its exact SHA in the independent terminal audit.
   A future unsealed successor can add a final disk-SHA equality check. Host
   `test_plan_drift` tests altered plan objects, not this late disk-file case.
3. **Nonblocking wording/coverage limit:** `checker.py:75-78` checks that any
   retirement after CTRL exit is the original `a001` park with no scalar/memory
   side effect, but final `:138` does not require `parked>0`. Thus README's
   "park required" means only post-exit rows, if present, must be park. An
   otherwise complete trace ending at the valid CTRL exit is allowed. The
   source exit/result gates remain intact; this is not a missing result oracle.

No change to sealed inputs is requested by this review. Conditions2/3 are
reported limitations, not measured failures. In particular, this preparation
must not be represented as independently verified service exit or live capacity.

## Exact Identities

All786 plan pins were independently hashed and matched actual files. The plan
contains every62 source READY evidence pin, every85 baseline pin, all66 image
file pins and all539 snapshot source pins with identical hashes; overlaps are
deduplicated in the786-entry map. Source/reference acceptance is not transferred
to DUT acceptance.

| Artifact | Actual SHA256 |
| --- | --- |
| prepared01/plan.json | `711e1f5ff862e9da4697ad3b6b2dfd278e78ec079f011b14665f4bfebb84d510` |
| prepared01/ready.json | `66effd34cc19017d02043fb65d9490b8f6057ddb7929e2c87503be1109f69a01` |
| replay.py | `5c88e2f9e880afcd9cb52c99f081b0301adab25a264c74e8bb1e9a5f7f98bca7` |
| checker.py | `b31d5ff38ce9b917d3cd3cf32c57337547e0be8b8b973a1a73ac3c6b42fe13a0` |
| test_host.py | `de0be34663e8818286a38eea3cea3d33320a32c239bea7c71b0a028aa78e6e25` |
| host01.json | `bf33ec138f7838820dca0a1cc62e0bc422c1bbc94e72b34088e5bf9dd39f4f1a` |
| M6 image.json | `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0` |
| M6 snapshot manifest | `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438` |
| Accepted source READY | `1fde3acbc776a3ce8b5ea40d20bfb4e46827758cacfacf5e0333c3d6d4526149` |
| Independent source REVIEW | `c1cc53ccf3848c8af2bb6004ea02517f00eb358eaebb6e6a6da49e5d27dbeb67` |
| Independent source audit.json | `5fd1d2e3add1f801d1d8f3ad9cd708848b41f445080ff63629231cc49897ae79` |
| Unchanged SoC ELF | `c4d681ad58bf1e46e121ffc3c3652cabc1b2a62100fc3987012c502e53fc89fd` |

Frozen image path is
`/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`;
its simv is `.../image/_build/vcs/simv`. Source/configuration/compiled-manifest
checks are inherited from `integration/replay_memory_regression.py:45` and
`gather_repair05/regression.py:84`. Actual configuration hash is
`6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.
These paths and helpers are pinned; no production worktree RTL is compiled.

## ei16 and Complete Oracle

`checker.specification` requires the actual ELF's13 instructions to equal the
accepted original helper, not merely its function name. Target is actual
`38880c57` at SoC PC0x80000aac, not vx. All three vset instructions must be
e16,m8,tu,mu. `retirement` enforces all13 exact encodings/order98 times and
rejects the target at another PC. Actual call a1 must equal `indices16`, not
the distinct ordinary `indices` address, even though e16 array values agree.

The pinned source model is the independently accepted original source-derived
model: original RNG/input, indices16, masks, old-vd91 and natural98 rows with
all97 predecessors. Each call checks2178 actual initialized scalar setup
values, actual argument values, three vset returns, target scalar/start/VL
arguments, exact csrw/csrr instructions and returned-vstart0.

Every call must have a unique actual LHU read for each of514 output/guard
positions after the entire helper. Missing, duplicated, misaligned or wrong
value checks reject. This includes all prestart, inactive and tail elements,
not only active data. Expected active-selected output is original
`input[indices16[i]]` for index<512, otherwise0; index is bounded by capacity,
not requested VL. Inactive OOR elements retain91. Counts are98 calls,
50176 results+196 guards,13x98 helper retirements and98 returned CSR checks.

Host ei16 discriminators use genuine model rows before injection:

| Call / element | Original meaning | Wrong value/pointer rejected |
| --- | --- | --- |
| Entry pointer | Actual a1 must name indices16 | Ordinary indices address |
|49 /2 | VL3/start1, index511 ->44879 | vx0 constant61881 |
|66 /255 | VL256/start128, terminal index512 OOR ->0 |61881 |
|98 /511 | VL512/start256, terminal index1 ->538 |0 |
|74 /255 | Sparse inactive index512 ->preserved91 |0 |

DUT CSV lacks the Spike raw vector-register dump; the strict runner uses actual
initialization, helper/CSR events and every scalar oracle load, not claims of
new DUT full-register-wave evidence. Generic frozen trace validation is also
required and rows/final-cycle/retirement totals must agree with the strict pass.
The original full-vector reference audit is separately pinned, not rerun here.

## Failure, Completion and Ownership

`checker.VETO` explicitly matches `RVV_PERMUTE_DETAIL`, including a partial line
with no final FAIL. It also rejects original full-child PASS, fail/abort/trap/
mismatch tokens and inherited fatal patterns. `replay.py:206` installs it into
the **actual frozen** `ara_verify.runner.FAIL_RE` before the runner starts.
Frozen `runner.py:174-219` reads new console bytes with a256-character carry
buffer, checks the regex before waiting for a newline/process exit, and polls
at0.1s. Its finally block terminates only the private process session, with
SIGTERM then SIGKILL fallback. Read exceptions also pass through this finally.

`checked_runner` latches the same abort Event for raw FAIL, strict-check
exceptions and late abort during checking. Jobs1 means there is no queued peer
to proceed after failure. Final checking requires exact COMPLETE/PASS1, exact
test membership/jobs/timeout/simv/trace mode, no exception, summary equality,
unchanged image/source/ELF/helper pins and unchanged parent approval. Both raw
logs must contain exact unique prefix/case/board/success markers with failure
veto; actual returncode0 and elapsed<=9000 are required. Private ELF SHA,
inputs manifest, cwd and exact NO_FSDB/seed1/COMMIT_TRACE command are checked.
CTRL store must be original exit instruction writing0 to0xd0000000.

`common.publish` masks SIGINT/SIGTERM for the terminal decision, checks sticky
abort and pending signals before writing/replacing complete.json, and can
downgrade pending success. The stored Host suite covers late abort and pending
signal rejection. This is not proof of later systemd service terminal status;
an eventual terminal audit must inspect that evidence separately.

Launch is gated before simulator creation by the plan SHA, explicit
`--authorize-run`, a separately hashed new parent-review JSON with exact plan,
unit, reference/source-review identity and `budget_risk_accepted=true`, plus
direct service identity and resource admission. Service check requires this
worker as MainPID, exact current cgroup ending in the named unit, active/running,
RuntimeMaxUSec `2h 50min`, KillMode control-group and Restart no. It supplies a
UID-owned user-bus environment after sanitizer removal. Missing/query-error/
wrong-parent service fails closed, not a fallback to an unbounded shell.

Resource admission counts live simv (comm or argv basename), jobs1 and unused
reservations, caps total at24 and requires at least32GiB MemAvailable. Only
disappeared processes are ignored; general OSError/permission failures are not
silently skipped. Reserved slots are sealed at0, not evidence that no external
reservation exists. Parent must coordinate that value; a needed nonzero value
requires a new reviewed plan. No capacity retry loop is present.

The exclusive launch.json create and fresh replay-directory requirement refuse
reuse. No image-build/retry path is used. `prepared01` currently contains only
plan.json and ready.json; ready's launch command retains unresolved parent-review
placeholders. This is preparation evidence, not observed simulator startup.

## Host32 Evidence and Limits

Stored host01.json is PASS_HOST_ONLY,32 tests, zero failures/errors,43.715s.
All32 test definitions have exactly one corresponding `... ok` log line, and
the test script SHA matches the plan. The reviewed tests include a full98
synthetic protocol fixture checked by generic+strict parsers, wrong setup/RNG/
arguments/helper/CSR/results/guard, the five ei16 discriminators above, missing
oracle/truncation, bad CTRL exit/park, ambiguous markers, budget/image/ELF/plan
object drift, parent approval, cancellation, COMPLETE and service/resource gates.

`test_actual_detail_stops_real_host_monitor` feeds the actual frozen monitor an
ordinary Python child which writes the real op20 DETAIL prefix without newline
and sleeps. Its assertions require failure_seen, nonzero exit, no timeout and
elapsed<5s, then sticky abort. The retained unittest log records it passed;
its temporary child log/per-test elapsed are not separately retained. This
review read that evidence and implementation; it did not rerun a child or simv.

Historical stopped tuple remains unknown. Natural98 is not the full2688 child,
full parent or Linux replay. Source/reference acceptance and this preparation
review do not transfer any old vx DUT PASS to this new ei16 ELF. Parent controls
the separate launch decision and any future terminal acceptance.
