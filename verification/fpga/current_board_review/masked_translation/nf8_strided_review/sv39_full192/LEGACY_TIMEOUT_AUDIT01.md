# Legacy Timeout Acceptance Audit

Read-only artifact audit after the independent timer/aggregate finding. No
simulator launched, repeated, stopped or modified. No old helpers edited.

## Selected NF8 Four

Input: `../sv39/vcs_candidate04_01/complete.json` SHA256
`793a633ad9572cc5990cebb6da592f87a4cf4c02eef12b240f3eba5614b27baa`.

Rechecked all old plan pins, exact four aggregate entries versus per-case
complete.json, runner summary.json, run.json COMPLETE, actual returncode0,
CSV oracle PASS, and exact trial membership. Aggregate firstfailure is null,
post_hashes UNCHANGED; recursive firstfailure.json membership is empty.

| Trial | Whole worker seconds | Runner seconds | Comparisons |
| --- | ---: | ---: | ---: |
|19|476.397692|470.107485|3122|
|17|448.986530|442.907842|3122|
|67|437.368757|432.245521|3166|
|31|327.666910|322.409533|2984|

Every whole-worker elapsed is strictly below1950s and every runner elapsed
below1800s. Result: SELECTED4_STRICT_ARTIFACT_AUDIT_PASS. These artifacts show
no occurrence of the identified timeout/cancellation race. The earlier full
CSV independent replay and terminal-service acceptance remain documented in
`../sv39/DUT_ACCEPTANCE.md`; this audit does not claim a new DUT execution.

## NF7 Full96, Still In Flight At Task Assignment

Do not modify its sealed script or infer acceptance from a live aggregate.
Only after a terminal event, independently require all of:

1. Exact owning service terminal success, MainPID0, no residual owned jobs.
   A collected transient unit requires independently pinned terminal evidence,
   not an assumption that missing means success.
2. Aggregate firstfailure is null and post hashes unchanged; no firstfailure.json
   anywhere in the run output. Any abort/timeout means NOT_ACCEPTED even if the
   old aggregate says PASS.
3. Exact24 groups/full96 trials, each returncode0, oracle PASS, complete real
   runner metadata and exact ELF/image identities; complete CSV/oracle replay.
4. Every group whole-worker elapsed strictly below2700s, and each runner within
   its fixed2400s budget. No timeout or cancellation labels in case/runner logs.

No new NF7 status query or acceptance is performed by this report. Missing
evidence is NOT_ACCEPTED, not a reason for an automatic rerun.
