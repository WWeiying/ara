# Independent e8 Prefix66 M6 Runner Review

Date: 2026-10-11. Reviewed
`../e8_m8_ops1_prefix66_vcs_m6_plan01/{HANDOFF.md,README.md,checker.py,replay.py,test_host.py,host01.json,prepared01/plan.json,prepared01/ready.json}`.
Only this report was written. No DUT/build/Spike/Host-suite launch, live-process or
service query, preparation command, or sealed-file edit was performed. The prior
accepted reference review was reused; neither large Spike trace was re-parsed.

## Verdict

**No new blocking runner/oracle defect found. Conditionally acceptable for the
fixed jobs1/9000s case/10200s service attempt, not an authorization to launch now.**
The existing requirements remain: genuine e16 terminal acceptance, a new pinned
parent review explicitly accepting budget risk, then runtime resource/service
admission. None of those live/dependency conditions was queried by this audit.

Approved-for-review plan identity:
`3d487be3a65775b2fa99cceec10bf9a09d9e2564e09efed66e7485a7abfa8006`.

Nonblocking qualifications:

- The e16 authorization gate consumes a parent-certified terminal and independent
  acceptance document, verifies their pins and completion/count contracts, and
  rehashes their raw evidence. It does not rerun the e16 raw CSV numerical checker
  or interpret the independent document's prose. The parent's actual independent
  acceptance must therefore precede its authorization JSON; a pinned file is not
  itself a substitute for that review.
- Inherited `checker.py:75-78,137` validates every observed post-exit retirement
  as the original side-effect-free park instruction, but does not require
  `post_exit_park_retired > 0`. The Host park negative corrupts an existing park;
  it does not test zero park rows. Do not describe this as proving at least one
  park retirement. Full66 checks, original CTRL exit0, simulator exit0/finish and
  terminal gates remain mandatory, so this is not a shortened-oracle acceptance.
- First-failure monitoring means first emitted error text. Original guard-only
  or returned-vstart-only errors need not emit an immediate DETAIL and can remain
  silent until final FAIL. No new live per-row CSV checker is claimed.

## Identity Checks

Plan SHA matches both HANDOFF and ready.json. There are785 plan pins. Independently
rehashed783 current files successfully. For the two already independently accepted
large raw Spike logs, reused the prior reviewed hash, verified the plan/reference
report hash agreement and actual file size, without reading their full contents:

| Reused raw reference identity | Bytes | SHA256 |
| --- | ---: | --- |
| e8 prefix66 commits | 177751012 | `5142c4d33cc38de9ac62c057f557d683e35e5ed1c960d18eff3bfde439a3fd3f` |
| e16 prefix98 commits | 129703748 | `3774dc8654b7e169ac370f063497a4b2aa291ee92aa26baf92b802d4b2420dd5` |

The worker itself retains full verify_pins calls before/after authorized execution.
This report does not mislabel reused reference evidence as785 freshly rehashed
files. All69 e8 READY evidence entries are present with unchanged hashes in the
plan; the old source/reference/independent-review identities remain bound.

| Current artifact | SHA256 |
| --- | --- |
| HANDOFF.md | `3e9708a46387a0f9b11e9c9ea18efc0ea424162520bbe8628203ad7365cf0f93` |
| README.md | `d59a0e0222818facdf3f345f48500d592ee79a1fa665aa304da2645a8a83fae2` |
| checker.py | `4da8e2fd64f40eb07f61fc8dda485eb17e7bc8276cb8a3e1c739e4656f1d1508` |
| replay.py | `c438af5ccff71eb31c5e08838817b4c86c0dc69fbac276ec4ddfe158fa9e6575` |
| test_host.py | `4a1c54aae67a90004a4c313e35d0d29fb4c3d67716c31dd44c203244a75019ff` |
| host01.json | `47fabc876f42aa7add0ae8d344014b83cacb8611297061c6b28278a4995dd5f7` |
| ready.json | `3bf1b35783c02b400a0a0371eb4ade1f65dd79f6bf84a5b1dcf4e8507868fd56` |

Existing SoC ELF remains
`791d817193c9b46eec48e6feee8b1d9c8ecf289b588253b21c1f59a54314d2c6`.
The image remains frozen M6, image.json
`a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`,
snapshot `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.
No new image or source build is requested. The prepared output contains only
plan.json and ready.json at review; this is a filesystem observation, not a query
of any live service.

## Scope And Full Oracle

Compared the e8 checker against accepted e16 plan02. Changes are the required
reference path, e8 SEW/byte addressing/LBU decoding, cap1024 and exact66 counts.
Explicit DETAIL rejection and all other strict checks remain. ELF-disassembled
specification was independently recomputed and exactly matches the pinned plan.

The [source/reference review](../e8_m8_ops1_prefix66_audit01/REVIEW.md) establishes
all65 predecessors, original RNG/setup,13 helper instructions and full-capacity
tu/mu oracle. No change to those sources or ELFs is needed here. The natural
endpoint remains tuple `[0,1,0,4,0,1]`, VL512/start256/scalar0, not a claim of an
identified historical stalled tuple.

`checker.py:49-141` requires exact13 instruction order/encoding and66 calls,
actual eight argument registers, full initialized source/index/index16/mask/
old-output arrays (4226 values/call), three vset returns/call, target scalar/VL/
start and returned vstart0. Every call requires the complete distinct1026 output
and guard byte positions through actual scalar LBU results. Thus67,584 result
bytes plus132 guards remain mandatory, including prestart, inactive and tail.
Successful original CTRL store and final exact counts are required.

Generic frozen CSV validation is additional. Row count, final cycle and retire
count must agree with the independent scalar-oracle decoder. Source identity is
not replaced by a synthetic direct-VFU test or a smaller expected-output range.

## Failure, Commands And Terminal Gates

The actual retained error is `RVV_PERMUTE_DETAIL ... expected=185 actual=184`.
Independent read-only evaluation confirms full and truncated-before-expected
forms match the explicit VETO. The wrapper installs the same expression into
the frozen runner's streaming monitor before running simv. Chunk carry and
0.1s scan cadence retain detection before newline/final FAIL.

The pinned Host27 report records PASS, zero failures/errors,36.228s. Reviewed its
source and log rather than rerunning it. The new real-monitor test uses an ordinary
Python child emitting the retained partial error then sleeping; it asserts
failure_seen, nonzero child exit, no timeout, elapsed<5s, exact partial output,
and sticky checked-runner abort. This is evidence about the actual monitor path,
not a DUT result or a new simulator run. Other Host negatives retain setup/RNG,
arguments/encoding, data/guard/CSR, missing oracle/truncation, exit/park, raw
PASS+failure, marker duplication, pin/plan drift, cancellation and pending-signal
coverage. Tests are focused controls, not exhaustive proof of every malformed
CSV or certificate.

Both console.log and run.vcs.log must contain exactly the expected PREFIX66,
case and simulator success markers, with failure veto even after PASS. Shared
check_artifacts additionally requires rc0, elapsed<=9000, private ELF hash/source,
actual M6 executable identity, exact private cwd/command, seed1, NO_FSDB and full
commit CSV. No UCLI, coverage, compile or automatic retry is permitted.

`replay.py:165-210` requires the pinned new parent review, exact plan/service,
budget-risk acceptance, e16 complete PASS/no-abort, same M6 image, old plan/source
pins, full raw-evidence pin membership, PASS1/rc0/budget, COMPLETE1/exact summary,
and strict98 counts. Approval evidence is recorded in launch.json and rehashed
after execution. Placeholder review arguments cannot authorize a launch.

At runtime, exact service MainPID/cgroup,10200s RuntimeMaxSec, KillMode=control-group
and Restart=no are checked through the trusted UID bus. Fresh resource admission
requires live plus unused reservations plus jobs1<=24 and available memory>=32GiB.
reserved_slots remains0; a changed reservation requirement needs a newly reviewed
plan. No live inventory was taken here.

Exceptions and non-PASS results latch abort. The wrapper checks COMPLETE/PASS1,
exact summary, image/pins and all raw evidence again, then uses the existing
signal-blocked terminal publication with pending-signal veto. A fresh launch.json
and replay directory prevent silent reuse/retry. Service-exit provenance still
requires post-terminal observation; worker status alone is not that evidence.

## Budget Assessment

Reference cost remains2,745,395 retirements. Applying documented rates gives
estimates, not bounds guaranteed for a different cap1024/M6 workload:

| Assumption | Estimated seconds |
| --- | ---: |
| Conservative historical273 retired/s | 10056.39 |
| Above plus20% time margin | 12067.67 |
| Earlier accepted M5 prefixes683.20..686.93 retired/s | 3996.62..4018.44 |

9000s requires at least305.04 retired/s without margin, or366.05 with20% time
margin. The9000s case and10200s outer service are both below3h; the latter leaves
1200s for validation/teardown but is not permission to exceed the case timeout.
The conservative estimate exceeds the case budget, while the comparable M5 rate
suggests a plausible roughly67-minute execution. Neither guarantees success.
The plan correctly records that risk and requires explicit parent acceptance;
a timeout must not automatically be classified as an RTL stall or retried with
larger limits. No source/oracle reduction is proposed.

**Final: no new blocking defect found; prepared runner conditionally acceptable,
launch remains gated. No full2688 child, exact historical-stall or Linux closure.**
