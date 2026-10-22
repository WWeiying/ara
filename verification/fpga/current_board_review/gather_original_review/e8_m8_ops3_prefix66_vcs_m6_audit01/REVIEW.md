# Independent e8 VI31 Prefix66 Runner Review

## Decision

**ACCEPTED_RUNNER_PREPARATION_ONLY_NOT_LAUNCH_AUTHORIZATION.**
No blocking finding in the sealed plan/runner/checker. Separate parent approval,
budget-risk acceptance and actual runtime admission remain required. No DUT,
Host/Spike rerun, build, live query, new raw parsing or sealed-file edit occurred.

Reviewed `../e8_m8_ops3_prefix66_vcs_m6_plan01/`; reused the independently
accepted source/reference audit, not a new interpretation of the original source.
[audit.json](audit.json) records identities, checks and limitations.

## Identity

| Input | Actual SHA256 |
| --- | --- |
| prepared01/plan.json | `edfd2c2f33fdbf76b9604efb6d98718a8f645fb0c8455ccda4cf9b8a2bf28d13` |
| prepared01/ready.json | `26884fe52a470ed0be90f9cb611009b3f2366001a35d2196fd28e2bbce845eb1` |
| replay.py | `a1373869a6e72623458a0915287da13b04f776abbc0e617cfed107ef9b01ebb3` |
| checker.py | `5b746dacc90791d05fc857f182c42ff35679872ded4fd8578382ee4f4e8efb43` |
| host01.json | `e4b22cc18075ed0a727c13c2396343db519ee61b563e55795859678f16d7c120` |
| SoC ELF | `88b154a9a1c68f2a25706eb7b8587237335b34d3bc69590f970fec0074fca841` |
| M6 image.json | `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0` |
| M6 snapshot.json | `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438` |

Independently hashed all **931 plan pins**, zero mismatches. Confirmed image
executable/support files, configuration, source manifest and snapshot bindings.
Plan spec equals the accepted source proof's actual SoC 13-instruction routine;
ELF and pass markers match. Ready command exactly matches the systemd command
suffix and plan SHA. Host log has exactly the 40 test methods in pinned source,
all recorded `ok`, zero failures/errors, 64.646s. These are stored outcomes,
not tests performed by this review.

## Oracle and Stop Gates

- `checker.py:22,50`: exact e8/m8/tu/mu 13 encodings, target `308fbc57`,
  unsigned imm31; ordinary indices pointer, a6=0 at entry and t3=0 at target.
  Actual helper includes original unused index load and move. Model is the
  pinned, independently accepted e8 source model, not e16/ei16 or vx.
- Exactly66 calls,65 predecessors, cap1024 and4226 initialized values per call.
  All1026 distinct result/guard addresses require **LBU** after complete helper;
  67584 result bytes+132 guards,66 zero returned vstarts,198 vset returns.
  Missing final element1023 tail read or a halfword load is explicitly rejected.
- Endpoint remains original tuple `[0,3,0,4,0,1]`, VL512/start256. Elements256..511
  require177; prestart0..255 and tail512..1023 retain91. Every earlier call also
  keeps full capacity. Source31 is valid even at VL1:177 differs from vx0=185
  and incorrect beyond-VL/signed-OOR zero. Host negatives discriminate those
  cases, ei16 dynamic substitution, pointer/encoding, prestart, inactive, tail,
  both guards, returned CSR, initialization, truncation and missing oracle.
- `checker.py:40,148`: both console and VCS log require exact unique prefix/
  board/simulator success markers, plus generic complete CSV validation and
  strict readback counts. DETAIL/FAIL/abort/trap mismatches veto even after PASS.
  Private ELF, original source path, exact image and command are verified.
  CTRL store must be original instruction/address with value0.
- `test_host.py:201`: the retained Host test calls the **frozen actual monitor**
  with a plain child emitting authentic partial RVV_PERMUTE_DETAIL, no newline
  or final FAIL. It requires failure_seen, nonzero exit, not timeout, under5s.
  Runtime extends that monitor's FAIL_RE with the same VETO. The monitor reads
  appended bytes with a256-character overlap and stops only its private process
  group; log-read exceptions also enter its finally cleanup.
- `replay.py:153,175,198`: errors/non-PASS set sticky abort; late cancellation
  after strict CSV processing changes PASS to CANCELLED. COMPLETE/PASS1 exact
  membership, successful returncode and matching summary are mandatory.
  Common publication blocks/checks pending SIGINT/SIGTERM and cannot knowingly
  publish PASS after abort. No retry loop, extra cases or build branch is used.

## Plan, Service and Resources

`replay.py:52` hashes the actual disk plan against approved SHA, then reads it
fresh and validates all pins/scope. `test_host.py:239` directly exercises this
function: valid disk content reaches validate; a later disk mutation rejects
before validate. Terminal code calls this gate, rechecks image and approval
pins, hashes artifacts, then atomically publishes complete.json.

Authorization binds the exact plan, unit, accepted source review/reference and
explicit `budget_risk_accepted=true`. Runtime requires direct service MainPID,
matching self cgroup/unit, active/running state, trusted explicit UID user bus,
RuntimeMaxSec10200, KillMode=control-group and Restart=no. Prepared command has
those properties; it neither starts a service nor supplies approval itself.
Exclusive launch.json and absent replay directory prevent output reuse.

One runtime admission counts live simv by comm or argv basename, adds jobs1
and unused reservations, requires total<=24 and available memory>=32GiB.
Only vanished-process errors are skipped; other read errors fail admission.
Plan reserved_slots=0 therefore assumes parent has no additional unused slots
to reserve at launch; parent must maintain coordination. No live availability
or actual service identity is claimed by this read-only audit.

## Budget and Limits

Fixed case9000s/service10200s/jobs1, seed1, NO_FSDB, no retry or automatic bound
increase. Reference cost2621149 /273 retired/s=9601.28s; plus20%=11521.53s,
above both the case bound and3h. This is a disclosed execution-risk decision,
not evidence the fixed budget will succeed. Parent-reported distinct M6 e8VX
4052s/~2.672M retired suggests roughly3975s at proportional throughput here,
but was not remeasured and does not guarantee VI31 timing.

Nonblocking evidence limits: scalar CSV verifies full memory readback plus
original instruction/argument/vset/returned-vstart chain, not directly all vector
registers or internal CSR values as the accepted Spike raw audit did. Original
park is required for every observed post-exit row, but no minimum park-row count
is required. Host service tests mock systemctl; runtime must still pass actual
ownership/resource gates. No full2688-child, Linux or exact historical-stall
closure is implied.
