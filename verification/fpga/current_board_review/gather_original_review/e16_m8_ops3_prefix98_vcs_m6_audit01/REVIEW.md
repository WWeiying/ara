# Independent vi31 M6 Runner Review

2026-10-11. **PREPARATION_REVIEW_ACCEPTED; no blocking finding for this sealed
plan. Not DUT launch authorization or DUT PASS.** Parent must separately
approve the exact plan/budget and perform runtime admission.

Reviewed `../e16_m8_ops3_prefix98_vcs_m6_plan01/`: HANDOFF, README, replay.py,
checker.py, test_host.py, stored Host37, plan/ready and transitive input pins.
Reused the accepted [source/reference review](../e16_m8_ops3_prefix98_audit01/REVIEW.md)
and the prior [ei16 runner review](../e16_m8_ops20_prefix98_vcs_m6_audit01/REVIEW.md),
with actual source diffs and unchanged shared-helper identities checked.
No Host/Spike/DUT execution, build/rebuild, live process/service query or old-file
write. The120MB raw was not reparsed; its bytes were only hashed as a sealed pin.
Only this new audit directory was written.

## Findings and Limits

- The prior terminal disk-plan gap is addressed: `replay.py:224-225` now checks
  `sha(out/'plan.json') == digest` and validates a fresh read after expensive
  testcase/summary checking, before publication. This is not just the old
  in-memory object check. **Coverage limitation:** stored `test_plan_drift`
  mutates plan objects; Host37 does not include a new run-level late disk-file
  mutation test. The new rejection path is statically reviewed, not newly
  executed by this audit. This is nonblocking.
- Inherited nonblocking wording limit: `checker.py:76-79` restricts existing
  post-CTRL retirements to original `a001` park with no scalar/memory side
  effects, but `:142` does not require at least one park row. A complete trace
  ending at valid CTRL exit is allowed. Do not describe this as mandatory
  observation of one park retirement or service termination.
- Budgets stay jobs1/case9000s/service10200s. Reference1905086 retired gives
  6978.34s at273 retired/s and8374.00s with20% margin. This fits the case budget
  arithmetically but is **not this case's measured VCS duration or a guarantee**.
  Outer1200s allowance covers setup/teardown/validation, not a proven worst-case
  bound. Parent approval still explicitly accepts budget risk; no auto retry
  or timeout escalation is present.

## Identities and Pins

All855 plan pins matched actual files. The map includes all62 source READY
evidence pins,148 baseline pins,66 image files and539 snapshot source files
with identical hashes (sets overlap). Source review, machine audit and auditor,
Host script/report, runner/checker, imported helpers, objdump, manifests and
compiled image are pinned. The source READY's historical PENDING label is
preserved; preparation separately requires the exact independent ACCEPTED
audit, rather than silently changing or treating PENDING as acceptance.

| Artifact | Actual SHA256 |
| --- | --- |
| prepared01/plan.json | `d35fd8ce0a1a74854ad6d230c2c9f467f7c633fa5d9f4f3d1ca52619fb23d0a5` |
| prepared01/ready.json | `05ba057dbb18f8b1d73f54656f90b632aa40452eed2aaaa39fbfd77dce29a253` |
| replay.py | `76a38135c13eb78578f3d0a4ef4c8003a8f858069859b4c0ccb9f51253c1765b` |
| checker.py | `fbb090d384e60b84568c11d5901bfdfb060d054a228c27405e61cda544330e84` |
| test_host.py | `41da26003c029e2e20ee0175bb33dcdb995fdae4cee54f40f4e0c3b063177862` |
| host01.json | `87d5fe02b8da1b1d69cab88294a73e16934726da9eeba06efbeaa9fb2028c0a4` |
| M6 image.json | `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0` |
| M6 snapshot manifest | `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438` |
| Source READY | `a354337fd4e6f2177b572db9ae372d580558fc55c12b21c1c05e3eac3f1bc672` |
| Independent source REVIEW | `7e198123638368bafea19c5160b9b88a8cbab55a4ccd67c416400e4ef5ba4fd2` |
| Independent source audit.json | `f7a31b0d7c0420ca78fb979875d38834a0cb19f064f7e77c20b37751c7c4ee22` |
| Exact SoC ELF | `c1064255efa0ff19d492d263723d1c7b88ad9521983ae07d12ecf8a753b5cf44` |

M6 image remains
`/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`.
Shared `gather_repair05/regression.py` SHA is unchanged:
`10358143c0b18f62bb4772aa9b0a117676eb9121d35bebbd80be7bd5e26c9966`.
Prepared directory contains only plan.json/ready.json; the template still has
parent-review placeholders. This is not evidence of actual service startup.

## Authentic Scope and vi31 Oracle

The single case remains original recovery177 e16m8 ops3 natural98, all97
predecessors, cap512, endpoint `[0,3,0,6,0,1]` VL512/start256. Original RNG,
setup, masks and scalar-slot0 are unchanged. Full2688-child and exact historical
stopped tuple remain unclosed; no recovery168 warmup or alternate sequence.

`checker.specification` reads the real SoC ELF and requires exact equality with
the accepted original13 encodings, including unused vle16 index load and
`mv t3,a6`. Actual target is `308fbc57`, `vrgather.vi v24,v8,31,v0.t`, at
0x80000764; all three vset instructions must be e16,m8,tu,mu. Full opcode
equality rejects vx, and the explicit immediate-field check requires31.

At each call entry, actual a1 must name ordinary `indices`, not `indices16`;
a6 must be0. At target, t3 must still equal scalar0 and immediate31 is required.
Every call checks2178 actual initialization values, including both index arrays,
predicate and full old output91. Missing bytes reject; no recorded expectation
is substituted for actual initialization evidence.

The accepted model requires `input[31]=32689` for every active-selected result,
even at VL1. This is neither input[0]=61881 from vx scalar0, literal scalar0,
signed-immediate/OOR zero, nor input[indices16[i]]. Outside `[vstart,VL)` or
under a false mask, expected is exactly91. Every514-element/guard position
must have one actual post-helper LHU read; missing, duplicate, misaligned or
wrong-value reads reject. Thus50176 results+196 guards, all13x98 instructions,
294 vset returns and98 returned-vstart0 checks are enforced, not only active
elements. Actual target arguments/VL/start and instruction order also match.

Host negatives assert genuine source coordinates before corrupting them:

| Call / element | Correct value | Rejected substitution |
| --- | ---: | --- |
|18 /0, VL1/start0 |32689|vx0 input61881; separately literal0|
|98 /511, VL512/start256 |32689|signed-immediate/OOR zero|
|49 /2, VL3/start1 |32689|ei16 dynamic index511 ->44879|
|33 /0, VL2/start1 |91|prestart overwritten32689|
|18 /1, VL1/start0 |91|tail overwritten32689|
|74 /255, sparse mask |91|inactive overwritten32689|

Both guards, wrong indices16 pointer, generic encoding corruption and explicit
vx funct3 substitution have additional rejection tests. The ordinary index
array is loaded but unused by vi31; its OOR values do not create an ei16-token
coverage claim. Source element31 is bytes62..63 inside128-byte v8, not a
physical-register boundary. Source/raw-vector proof is reused from the accepted
audit; this runner's DUT CSV gate uses initialization/helper/CSR/scalar checks,
not an invented DUT vector-wave observation.

## Host37 and Immediate Failure

Stored host01.json records37 tests PASS, zero failures/errors,44.951s. Its
script hash matches actual test_host.py and the plan. All37 AST test definitions
have exactly one corresponding `... ok` entry. The positive full98 synthetic
protocol fixture passes generic and strict checkers; negatives additionally
cover setup/RNG/arguments, vstart, missing oracle/truncation, exit/park, marker
ambiguity, ELF/image/plan-object/budget drift, parent approval, abort and service
query failure. These are stored checker tests, not new DUT results; none were
rerun by this review.

The genuine source Host failure line begins
`RVV_PERMUTE_DETAIL op=3 seed=0 scalar=0 vl=1 mask=0 element=0 vstart=0`.
The actual frozen monitor test writes this partial line without newline or
final FAIL through an ordinary Python child. Stored PASS covers assertions for
failure_seen, nonzero child exit, no timeout, elapsed<5s and sticky abort.
The temporary child log/per-test elapsed is not retained separately; this audit
does not claim an independently rerun timing measurement.

Runtime installs the same explicit DETAIL veto into frozen runner.FAIL_RE before
running. The monitor scans byte chunks plus carried text without needing a
newline, at0.1s intervals. Failure/read-exception/timeout/cancel paths terminate
the private process group via the monitor's finally block. Strict raw checks
reject FAIL/DETAIL/TRAP/ABORT/MISMATCH even after PASS, and reject misleading
original full-child PASS. Both console.log and run.vcs.log require exact unique
prefix/case/board/Core-success markers. First failure sets sticky abort; there
is only one job and no retry.

## Admission and Terminal Contract

The worker requires exact initial plan SHA, explicit --authorize-run and a new
hashed parent review with `AUTHORIZE_E16_VI31_PREFIX98_ONCE`, exact plan/unit,
source READY/review identities and budget-risk acceptance. Merely preparing or
accepting reference evidence cannot reach launch. Unit is
`ara-gather-e16m8-vi31-prefix98-m6-01.service`.

Before simulator creation, direct service identity must be this worker's
MainPID and exact cgroup, active/running with RuntimeMaxUSec `2h 50min`,
KillMode control-group and Restart no. Trusted UID bus environment is restored
explicitly; service query errors fail closed. These checks were not called
against live services in this review.

Resource admission counts actual simv plus jobs1 plus unused reservations,
requires total<=24 and MemAvailable>=32GiB, and ignores only disappeared
processes rather than swallowing general OSError. Reserved slots are sealed0;
parent must ensure this matches its allocation, or prepare a successor plan.
No live capacity is inferred from prepared status and no auto-retry admission
loop exists. Exclusive launch.json and fresh replay directory refuse reuse.

Private ELF, source path, image identity, cwd and exact seed1/NO_FSDB/full-CSV
command are checked. Returncode0 and elapsed<=9000, original CTRL exit0,
generic/strict CSV count agreement, COMPLETE/PASS1 membership/jobs/timeout,
summary equality, rehashed disk plan and unchanged source/image/helper/parent
pins are all prerequisites for final PASS. Sticky abort during expensive
validation or a pending signal at publication downgrades to NOT_PASS. Existing
signal-aware publication is unchanged from the independently reviewed helper.

An eventual terminal audit still needs actual raw/CSV/input/evidence hashes,
the original plan SHA and independent service-exit evidence. This preparation
review provides none of those future execution results and does not authorize
the parent to omit its separate DUT admission decision.
