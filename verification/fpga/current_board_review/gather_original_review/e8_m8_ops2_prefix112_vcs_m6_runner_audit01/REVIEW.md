# Independent Prepared Runner Admission Review

Decision: NO_BLOCKER_FOR_PARENT_CONDITIONAL_ADMISSION, not DUT PASS and not
launch authorization. Reviewed the actual prepared01 plan, not the earlier draft.
Parent must separately approve this plan, explicitly accept budget risk, and
pass the runner's runtime resource admission. No resource query was performed.

## Frozen Identities

| Input | SHA256 |
| --- | --- |
| prepared01/plan.json | bb3b5302ce2c65ec91874c22ed85705488aae4ba2043ad32b285ba60c6d81c11 |
| prepared01/ready.json | 880682355e85e9cccb7b4ba12167bc1a04a1e18e59a4052fd8898dbf14344d94 |
| replay.py | 0409776216fe0eae514ffe715540663b31414d68ef10e8ec7cc5983cd95631e5 |
| checker.py | 77683517a53ff02666068b6176eebe3df7eb2f74daaefa914d3ad1536e93cff7 |
| test_host.py | 892b298f63f4c3a7a0fa188a074319d3616aedbf2c48ea171c2e7a28ff70b4df |
| host01.json | 67702527d52c99ab458bbe870b7643732b92aaf9af4dd8902ac9f54af1ae7681 |
| audit02/REVIEW.md | dcfc682bfb94597c210c88b05c2469a01b6bfbde8c6f0cbd88a483290ef53bd9 |
| audit02/audit.json | e4fa3b3850826cec964014821c9e497917df60c86542d7a08f2e603f4be1ed5b |
| M6 image.json | a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0 |
| M6 snapshot.json | 3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438 |
| unchanged SoC ELF | a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74 |

Independently streamed and hashed every one of 1098 plan pins: zero mismatch,
2100334783 bytes read, 12.302325 seconds. Verified exact inclusion without digest
conflicts of all 410 reference input pins, 22 reference artifact pins, and two
audit02 prior-evidence pins. All 539 frozen M6 source files and 66 image files
are included. Pinned compiled manifest has 453 entries. Plan/ready identity and
source-proof/ELF/13-instruction membership agree. No build or disassembler run.

## Host And Architectural Gate

Stored Host result is PASS_HOST_ONLY, 55 tests, zero failures/errors, 198.761s.
All 55 test method names match recorded successful log entries; test script SHA
matches current source and plan. Host was not rerun. Its record directly pins
test_host.py; current checker/runner and transitive helpers are pinned by the
prepared plan, not by a separate historical imported-module manifest in Host.

Read audit02's accepted source/reference report and its pinned evidence; did not
repeat its complete Spike parse. Acceptance remains source/reference only.
The runner binds actual audit02 SHA values, accepted counts, pure-park controls,
successor READY, and unchanged ELF; the former None/draft gate is resolved.

The DUT checker requires all original 112 calls, including all 111 predecessors,
in original order. CAP=1024; every call needs all 1024 distinct result-byte LBU
reads plus both guards after all 13 helper instructions, for 114688+224 total.
The last call's missing 78 results plus two guards cannot be hidden by having
already executed its target. Source/index/predicate/output initialization and
arguments are checked each call; original vset encodings, actual return VL,
vstart argument and zero returned-vstart are checked. Target is VI0 30803c57 at
SoC PC 0x8000071a, not VX or VI31; source0=185 and preserved bytes=91.

Seven original VLs x four masks x four restart trials are retained, including
duplicate VL1024 starts [1,512,1023,1023]. Exact 13 opcode sequence and SoC PCs
match pinned source_elf_proof; original Linux helper encodings match that proof.
The oracle uses full prestart/tail/inactive preservation, not active-only checks.
Host negatives cover last80, upper512, final guards, upper-active/inactive,
nonzero returned-vstart, wrong target/exit, old66-only and original-park effects.

## Runtime, Exit And Cancellation

Exact one-case COMPLETE/PASS/rc0, empty reason, private ELF, actual image/command,
console and raw VCS log, nonempty generic-valid CSV and independent CSV counts
are required. Exact console markers are singletons; failure, DETAIL, abort,
trap and parent-program markers are vetoed even after an apparent PASS.
SoC CTRL exit must be original sd at 0x80000072, address 0xd0000000, value zero.
Afterward only original self-loop at 0x80000076/a001 with no GPR/memory effects
is accepted. This is separate from reference HTIF value1 and its park address.

End-of-run checks freshly hash/read plan.json, validate all plan pins, recheck
image and parent approval pins, and hash raw result artifacts. Checker exceptions
or non-PASS results latch abort; cancellation during strict checking changes PASS
to CANCELLED. Existing shared publication blocks SIGINT/SIGTERM during its short
decision/write, checks latched/pending signals and publishes NOT_PASS on abort.
Expensive CSV and pin verification are outside that publication section.

Jobs=1, case=9000s, service=10200s; no build, retry or FSDB. Exclusive launch.json
and fresh replay directory reject reuse. Service gate checks loaded/active/running,
exact unit, current MainPID, own cgroup, RuntimeMaxUSec=2h50min, control-group kill,
Restart=no. Sanitized environment gets explicit user-bus variables. Resource
admission is deferred to run, uses one slot plus live/external reservations and
memory floor. Plan reserved_slots=0 must still match parent's actual roster.
No historical service exit is claimed by this pre-launch review.

## Limits

Budget remains a risk, not a guarantee: conditional VX proxy 7585.72s, plus20%
9102.86s exceeds case9000; slower273-retire/s assumption gives18325s. The parent
authorization gate explicitly requires budget_risk_accepted=true. No automatic
budget increase, fallback, retry, or reference-step-to-DUT-limit substitution.

Even a future PASS covers only first112 of2688 original child calls, first
seed/scalar slot, leaving2576 beyond this prefix. It does not close the original
Linux run, the unknown historical stopped tuple, or full-child acceptance.

Review actions were read-only source/JSON inspection and file hashing. No Host,
Spike, DUT, build, resource/live-process query, or Tesla helper edit was performed.
Only this new independent report was written.
