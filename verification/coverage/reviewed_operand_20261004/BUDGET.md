# One-Shot Budget Plan: Code Preparation Only

The **900-second total run /880-second DVE ceiling** is the coordinating agent's
planning decision under user-authorized preparation for this NEW, unrun capture
and report. The user did not explicitly specify these numbers or explicitly
accept the execution risk. This decision is NOT permission to launch. It
supersedes the earlier280-second capture limit and the withdrawn1500-second
proposal as a preparation-time technical choice.
No old frozen wrapper is changed. This document and the code are preparation,
not approval of a particular snapshot or a request to launch DVE now.

## Allocation And Enforcement

| Work | Bound or allowance | Meaning |
| --- | ---: | --- |
| Future prepare/admission | 300s | Separate bounded command; includes current-tip admission and snapshot construction |
| Planned future run, all work | 900s | Includes approval validation, prechecks, one tool session, postchecks and cleanup |
| Prelaunch | 40s ceiling | Reject before tool launch if exceeded |
| DVE | 880s maximum | Actual timeout is computed once from remaining total budget |
| Postchecks | 15s reserved before DVE | Estimated reserve, not a measured or guaranteed sufficient duration |
| Cleanup | 3s reserved | Process-group kill/wait; incomplete preservation checks cannot publish success |

The actual DVE timeout is `min(880, floor(900 - elapsed - 15 - 3))`.
The total-run alarm is set from the original start time, not restarted after
validation or after DVE. Early tool completion gives postchecks more time;
the15-second reserve is a minimum remaining allowance at launch, not a separate
cap. Publication still requires all four full input-integrity sweeps, native
proof, latest-tip check, snapshot/receipt pins and final preserved inputs.
Any insufficient time, failed audit, changed tip or tool timeout rejects the run.
No gate is skipped and no automatic retry or cap increase exists.

These are overlapping ceilings/reserves, not additive880+40+15+3 allocations.
Prepare plus run allows at most1200s of active work per independently approved
stage; waiting for independent snapshot review is not tool execution. The
compiled+one-PASS capture and the later single combined full-corpus report are
separate stages requiring authorization, never two alternative waiver policies.

## Existing Measurements Only

| Existing observation | Seconds |
| --- | ---: |
| 648 read-only complete admission | 151.608 |
| 641 full hierarchy: selected tests to summary | 197.608159227 |
| 645 full hierarchy: selected tests to summary | 184.642880588 |
| 18-point/3-scope native pilot, whole process | 50.986 |
| Initial empty to saved native | 8.488188134 |
| Saved native to reset empty | 4.059089967 |
| Reset empty to roundtrip native | 3.783083849 |
| Roundtrip native to final empty | 3.628080414 |

The four native phase deltas sum to19.958442364s. They mix GUI inventory,
selection, exclusion, recalculation, native serialization and Python checks;
they are NOT individual API service times. The50.986-minus19.958 remainder
(31.027557636s) also mixes setup/teardown and cannot isolate startup cost.

The new capture has7272 fresh metadata leaf visits,216 scope activations,
3612 exact selections,2468 exclusion queries and1144 per-point excludes.
The pilot had1818/18/1533/1515/18 respectively. Native record count also grows
18 to1144. Metadata caching and exact-group zero proofs reduce repeated work,
but do not justify assuming every later phase scales only with scope count.

For scale only, applying63.5556x to the entire mixed native phase span and
adding the observed remainder gives about1299.50s. That is a conservative
diagnostic, NOT a prediction or proven lower/upper bound. It shows why neither
280s nor880s completion can be guaranteed from these observations. The earlier
708s proxy underweighted native parsing/import in later phases and is withdrawn.

The report has two full exports and loads one composed native union; it does
not repeat1144 individual native-discovery exclusions. Two198s allowances plus
12x the old mixed state span plus50s allowance gives about685.50s as a rough
planning estimate. Loading growth, four runtime integrity sweeps and scheduling
are not isolated by these measurements; this is also NOT a runtime guarantee.

## Planning Decision And Future Sequence

The coordinating agent selected the900/880 cap while preparing a possible
single-attempt workflow. Runtime uncertainty remains; this is neither explicit
user risk acceptance nor permission to launch. Do not reinterpret the cap as
a completion guarantee or perform an unauthorized DVE run to test the estimate.

After the current batch is COMPLETE and authorization is renewed, perform one
prepare on the actual latest completed PASS tip, obtain independent review and
a parent receipt for that exact snapshot, then make at most one bounded attempt.
No automatic re-admission on each tip movement and no historical648 rescan now.
Only after independently qualified full1144 native capture may the later report
snapshot be prepared/reviewed and the single1345-point report run authorized.

Current status: ready for code/budget review and FUTURE prepare only. No actual
snapshot, DVE invocation, native1144 qualification, waiver application or adjusted
coverage claim is created by this plan. Receipts bind actual independent review;
they are not human signoff or approval of arbitrary future manifests.
