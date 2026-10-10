# Coverage Closure for the Frozen RVV/QBS/AKV Design

## Objective and current evidence

Improve coverage of executable product logic with independently checked tests.
The October 1 baseline contains 620 PASS VDBs from one VCS image. Its raw
ara_tb line/condition/branch/FSM/toggle results are
76.88 / 78.94 / 77.22 / 50.54 / 59.63 percent.
This is a starting point, not evidence of complete verification.

Use `ara_dsa_signoff_integration` as the active verification worktree. Preserve
the existing corpus, simulator and checkers. Full RTL Linux boot and physical
implementation are outside this coverage campaign.

## Acceptance targets

For the product configuration, aim for at least 90% line, 85% branch and
condition, 95% reachable FSM state and 90% reachable FSM transition coverage
in the selected execution/control blocks. Aim for 85% toggle coverage of
active control and handshake signals. Report datapath toggle separately;
constant parameters and unimplemented configurations are not stimulus gaps.
These are work targets, not a claim that current evidence meets them.

Do not replace the raw denominator with a guessed reachable denominator.
Waivers require exact instance/point identity, configuration/source evidence
and review. Keep DVE raw and waived reports side by side. Never exclude a
reachable feature because it is hard to exercise or a test currently fails.

Functional closure also requires explicit evidence for each supported
instruction family, legal configuration and exception/recovery category.
Case counts and code coverage alone cannot establish this. New failures stay
in the issue ledger until independently resolved or explicitly scoped out.

## Coverage-driven sequence

1. Validate the simulator/source/checker identity and the existing PASS ledger.
   Rank actual missing RTL decisions; classify configuration-disabled and
   tied-off paths before writing stimuli.
2. Add short tests with a falsifiable target and independent expected result.
   Precheck standard instructions in Spike; check custom operations against
   their independent numerical/descriptor reference.
3. Run at most eight VCS cases at once. Keep each result directory unique and
   each case bounded. Continue independent cases after functional failures in
   exploration mode; stop on infrastructure or evidence drift.
4. Admit only complete, audited PASS VDBs. Merge them with the exact old corpus
   once. Report DVE increments per full hierarchy and per-case diagnostic
   bitmap gains. Do not repeat the old corpus unless RTL/configuration changes.
5. Use the measured gains and remaining holes to select the next batch.
   A case with no new code points may still provide functional evidence, but
   does not justify blind expansion of the same stimulus family.

## Initial gap selection (620-test baseline)

| Area | Evidence to inspect | New stimulus direction | Independent check |
| --- | --- | --- | --- |
| Scalar decoder | Compressed decoder line 50%, branch 44.19% | Missing legal compressed families and reserved encodings | Exact register/memory values and traps; Spike |
| CSR control | CSR branch 27.96%; missed access/privilege decisions | M/S/U privilege, counter permissions, illegal/read-only accesses | Cause, EPC, TVAL and architectural side effects; Spike |
| Ordinary RVV | Queue-specific conversion/boundary decisions | Only supported conversion, mask and alignment combinations absent from the corpus | Element, mask/tail and CSR checks; Spike |
| QBS/AKV | Profile/descriptor/shape conditions and remaining FSM paths | Valid boundaries and rejected descriptors with recovery | Independent arithmetic/descriptor oracle and ordinary RVV handoff |

The exact next set is selected after source and VDB inspection, not solely
from these aggregate percentages. In particular, low operand-queue coverage
can include disabled conversion modes, and low QBS FSM coverage can contain
unreachable state transitions rather than missing compute workloads.

## Evidence and reporting

Each batch saves frozen input/source hashes, simulation commands, bounded
logs, independent checks, and VDB identity. `all-passed-outcomes.json` contains
the complete aggregate ledger. `coverage-delta.json` uses official DVE values;
`per-case-gains.json` records ordered incremental raw bit gains. The latter is
diagnostic and must not be called architectural functional coverage.

The goal remains open while applicable coverage gaps or unresolved correctness
issues remain. A passing batch, a larger test count, or an improved percentage
is progress, not signoff by itself.

## October 4 measured control extension

`verification/out/gap35-control-current-20261004-01` contains six new tests:
five PASS and one 180-second wall-clock timeout (`csr_gap35_permissions`).
Only the five PASS databases join the old 620, giving 625 admitted tests.
The timeout has no admitted coverage and is not a proven RTL defect.

| Official DVE metric | 620 baseline | 625 admitted |
| --- | --- | --- |
| ara_tb line | 76.88% | 76.90% |
| ara_tb condition | 78.94% | 78.96% |
| ara_tb branch | 77.22% | 77.24% |
| ara_tb FSM | 50.54% | 50.54% |
| ara_tb toggle | 59.63% | 59.63% |
| Compressed decoder condition | 75.00% | 100.00% |
| Compressed decoder branch | 44.19% | 51.16% |
| CSR condition | 33.45% | 38.88% |
| CSR branch | 27.96% | 29.39% |

These are raw, unwaived values. The system subtree gained 28 raw line,
43 condition and 26 branch bits. Raw diagnostic bits are not DVE denominators.
The compressed ALU/control companion passed but contributed no additional
line/condition/branch/FSM points in this batch's ordering. Retain it as
functional evidence, but do not expand similar ALU tests merely to raise counts.

The per-case gain file attributes shared new points to the first admitting
case in selection order. It is not each case's independent gain over the
original baseline. Official aggregate deltas are order-independent.

Further point-location review found that the frozen `vcs_point_audit.py`
branch-vector ordering is not reliable for this VCS image. Preserve the old
script and reports as historical evidence; do not use their decoded missing
branch labels alone to select tests or waive points. Explicit line-block
coordinates and independently checked per-spec branch ordering must agree.
FSM source attribution also needs validation before claiming specific missing
transitions. DVE percentages and raw OR/popcount totals do not depend on this
source-location interpretation.

### Inline observation versus product logic

The 625-test bitmap ranks `operand_requester` among the largest line gaps.
Source-bound inspection finds that its raw count includes substantial inline
`FOR_VERIFY` observation code, not only execution logic. The native source ID,
compiled source hash, line-block indices and every statement coordinate were
checked before classifying a block as a candidate.

| Lane | FOR_VERIFY candidate blocks hit/total | Remaining mapped blocks hit/total | Unmapped raw positions hit/total |
| --- | --- | --- | --- |
| 0 | 237/776 | 390/474 | 21/21 |
| 1 | 237/776 | 417/474 | 21/21 |
| 2 | 237/776 | 420/474 | 21/21 |
| 3 | 237/776 | 420/474 | 21/21 |

These are raw diagnostic line-block positions, not DVE line percentages.
Evidence is `out/gap35-analysis-20261004-01/inline-requester-candidates.json`,
generated by `inspect_inline_observers.py`. Membership in `FOR_VERIFY` alone
does not prove that excluding a point is safe. Review the signal fanout and
native exclusion identities before any policy change. No waiver is applied
by this inspection, and no functional queue, hazard or exception path is
removed. Ordinary arithmetic tests should target the remaining reachable
functional branches rather than debug-plusarg-controlled print paths.

## October 4 measured vector/custom extension

`out/gap35-vector-checked-preflight-20261004-03/collection.json` admits five
additional PASS cases, bringing the same-image corpus to 630. Its directory
name predates launch and does not mean the results are only a preflight.

| Official raw DVE metric | 625 admitted | 630 admitted | Increase, percentage points |
| --- | --- | --- | --- |
| ara_tb line | 76.90% | 76.94% | 0.04 |
| ara_tb condition | 78.96% | 79.04% | 0.08 |
| ara_tb branch | 77.24% | 77.28% | 0.04 |
| ara_tb FSM | 50.54% | 52.96% | 2.42 |
| ara_tb toggle | 59.63% | 59.68% | 0.05 |
| QBS engine FSM, including children | 64.57% | 78.74% | 14.17 |
| QBS compute-engine FSM, including children | 60.09% | 76.23% | 16.14 |
| QBS FP accumulator FSM | 56.25% | 75.00% | 18.75 |

The targeted QBS wide-row/tail case contributes 36 new raw FSM positions and
150 condition positions in selection order. CSR permission checks contribute
41 line and 21 branch positions. This is evidence of exercised new behavior,
not a denominator change or a waiver. The mask-tail, vector-CSR and no-op
memory companions also pass, with smaller measured code-coverage increments.

The same batch exposes unresolved functional failures. They are retained in
`out/gap35-analysis-20261004-01/failure-triage.json` and not counted as coverage:

- `vgap35_carry_ta`: three active carry/borrow-result bits differ at vstart=61;
  the fixed restart-capable Spike and independent arithmetic reference agree.
- `vgap35_slide_bound`: large VSLIDEDOWN offsets at vstart=3 overwrite preserved
  prefix elements 0 and 2. Static output-BE gating is a hypothesis, not yet a
  measured cycle-level root cause.
- QBS/AKV descriptor and reserved carry-encoding tests reach bounded timeouts.
  A timeout is not by itself proof of RTL deadlock. Inspect last committed
  progress and exact test work before assigning any retry budget.

### Next control-state test

The prepared `fence_t_gap36_smoke` targets controller FENCE.T flush, drain,
padding-zero and microreset return behavior. It is M-mode/Bare, IRQ-off,
scalar-only, with no in-flight accelerator requests. Two real instructions
must preserve all GPR/FPR values, selected CSRs, memory and exact PC+4 resume.
The 458-check architectural identity test cannot alone distinguish a hardware
NOP: `run_fence_checked_extension.py` also checks retired opcodes and native
controller coverage. Its static ELF audit and negative-validator tests do not
constitute DUT PASS. Do not claim accelerator draining, security properties,
arbitrary padding, or measured new coverage before the VCS result is admitted.

The first VCS execution (`gap36-fence-current-20261004-02`) completed its 458
selfchecks, but the strict commit audit found duplicated resume records in
both rounds. The run is rejected as an admission/infrastructure anomaly and
contributes no coverage. Separate trace-generation versus execution analysis
is required before changing the checker or blaming RTL.

The subsequent read-only diagnosis in
`out/gap36-fence-diagnosis-20261004-01` identifies stale legacy tracer issue
queues across microreset. The independent RVFI CSV has each fence/resume
instruction once, while 127 legacy rows carry displaced instruction labels.
At the same recorded cycles, apparent repeated AUIPC writes are actual store
retirements in RVFI. All 11,526 RVFI opcodes match the frozen ELF, and both
capture sequences store the expected values. Native controller transition
assignments are also exercised. This is strong observer-defect evidence, not
permission to filter the old trace or retroactively count its rejected VDB.
Exact tracer queue contents and reset edges were not captured in this run.

### Bounded descriptor and privilege successors

The three earlier timeouts do not justify a uniform timeout increase:

- QBS descriptor retirement continued through 3965 of 4954 checks. The
  identical ELF receives a measured-work-based 600-second completion budget.
- The full AKV descriptor test projects well beyond ten minutes. Six new
  groups partition its 23 mutations exactly once. Each retains full register
  guards, fault checks, and a valid fill/load/release recovery sequence.
- The illegal carry test faulted on `mtvec` setup in U mode before testing
  its target instructions. A new testcase moves the identical 555 checks to
  the existing M-mode CRT hook. Its Spike precheck separately proves M-mode
  setup, the four intended traps and entry into a U-mode result gate; the two
  platform ELFs are not claimed to be identical.

The new batch uses the same RTL image and 630-test baseline. Host/Spike
prechecks permit starting VCS, not admitting its future result. The source,
precheck, ELF and original-failure evidence remain separate and immutable.

### Current native waiver application

`out/dve-reviewed-630-20261004-01` completed successfully with native DVE
`APPLIED`. Its exact saved set is 94 reviewed point exclusions plus 10
verification-observer instances. The original 630-test raw report is unchanged
at every hierarchy row; no failed test, guessed denominator or new inline
observer candidate was added. The snapshot contains the source/shape review,
input hashes and native exclusions for reproduction.

| ara_tb metric | Raw | Reviewed exclusions applied |
| --- | --- | --- |
| Line | 76.94% | 76.85% |
| Condition | 79.04% | 79.04% |
| Branch | 77.28% | 77.28% |
| FSM | 52.96% | 52.96% |
| Toggle | 59.68% | 60.61% |

Line coverage decreases because removing highly covered verification observers
also removes their hits. This is a scope correction, not an execution
regression. Waiver changes must never be described as stimulus improvement;
the coverage-extension sequence continues comparing raw reports.

## October 4 measured descriptor closure

`out/gap36-timeout-current-20261004-01` completed with eight new independent
PASS results and a 638-test admitted DVE report. All six AKV groups, the
corrected-privilege illegal carry test and the identical-ELF QBS descriptor
retry passed within their bounded budgets. No old timeout VDB was reused.

| Official raw DVE metric | 630 admitted | 638 admitted |
| --- | --- | --- |
| ara_tb line | 76.94% | 76.95% |
| ara_tb condition | 79.04% | 79.06% |
| ara_tb branch | 77.28% | 77.31% |
| ara_tb FSM | 52.96% | 52.96% |
| ara_tb toggle | 59.68% | 59.71% |
| QBS descriptor decoder line | 73.33% | 91.67% |
| QBS descriptor decoder condition | 72.00% | 90.00% |
| QBS descriptor decoder branch | 37.04% | 81.48% |
| AKV engine condition, including children | 73.62% | 77.79% |
| AKV engine branch, including children | 95.20% | 95.85% |
| Dispatcher branch | 85.35% | 85.74% |

These gains close real descriptor/exception decisions despite the small
whole-SoC percentage change. The 638-test report is raw; the separately
reviewed waiver report above still describes 630 tests, not 638.
Neither the failed carry restart/slide-prefix cases nor the rejected legacy
FENCE.T observation run is admitted. The remaining campaign targets control
paths and reachable operand-queue decisions rather than more copies of the
now-covered descriptor cases.

### Reachability review after 638 tests

The queue review in `out/gap38-queue-analysis-20261004-01` finds no additional
ordinary-request reachable branch in the ALU-A/MFPU-A queue misses examined.
The remaining paths are constrained by operand routing, supported element
widths/conversions, lane identity, or constant FIFO/LZC inputs. Low raw queue
percentages therefore do not justify another broad arithmetic sweep.
These are source-level reviewed candidates, not applied waivers or formal
proof of all possible protocol behavior.

One executable gap remains in lane 3 MFPU-B: int8-to-FP16 widening with VL=36
targets Branch 5(35), raw index 41, and Blocks 116/117, raw indices 120/121.
Other lanes already cover that conversion arm. A short signed/unsigned test
with an integer-derived IEEE binary16 oracle, source preservation, tail,
guards and flags is the selected next stimulus. Gains remain unmeasured.

The independent CSR review in `out/gap38-csr-reachability-20261004-01`
identifies 142 line Blocks and 108 branch vectors constrained by RVH=0,
XLEN=64 or zero implemented PMP entries. Every selected point is zero in all
638 admitted tests. It explicitly preserves 58 corresponding illegal-access
rejection paths and does not waive debug access, interrupt state, TVM, or
performance counters. No policy is changed: native DVE saved-point identity
and an independent exclusion review are required before application.
Unreachable-point classification and new stimulus coverage must stay separate.

## October 4 measured FENCE and CSR control closure

`out/gap37-control-current-20261004-01` is complete with 640 admitted PASS VDBs.
Both new simulations passed independently: FENCE.T has 458 architectural
selfchecks, exact direct-commit capture evidence and native controller
activity; the CSR alias/TVM case has 626 selfchecks and its strict admission
contract. The old 638 cases were not rerun. The rejected legacy-observer
FENCE run and both unresolved vector failures remain excluded.

| Official raw DVE metric | 638 admitted | 640 admitted |
| --- | --- | --- |
| ara_tb line | 76.95% | 76.98% |
| ara_tb condition | 79.06% | 79.07% |
| ara_tb branch | 77.31% | 77.33% |
| ara_tb FSM | 52.96% | 53.44% |
| ara_tb toggle | 59.71% | 59.72% |
| CVA6 controller line | 65.82% | 77.22% |
| CVA6 controller condition | 30.77% | 50.00% |
| CVA6 controller branch | 50.00% | 65.52% |
| CVA6 controller FSM | 0.00% | 62.50% |
| CSR line | 46.90% | 47.90% |
| CSR condition | 39.93% | 40.81% |
| CSR branch | 32.75% | 34.03% |

The original postprocessing stopped at a strict proof comparison: JSON
converts the two FENCE capture dictionaries' integer keys to strings. An
independently reviewed report-only finalizer permits precisely those two
65-key conversions, reconstructs all original checks and proves every other
field unchanged. It then calls the unchanged checked aggregation path. The
original checkpoint is archived, both worker outcomes and VDBs are untouched,
and the collection binds the recovery evidence. This is an aggregation repair,
not a relaxed architectural check or a new RTL simulation.

The separate CSR reachability review at
`out/gap39-csr-waiver-review-20261004-01/review.md` accepts 250 exact candidate
coordinates semantically, but applies none. Of these, 248 have constant-guard
proofs; two PMP read-format points require the normal reset-driven, unforced
state invariant. All 58 paired absent-feature rejection paths, ordinary
privilege/trap handling, debug, TVM and counter logic remain in scope. Exact
native saved-point identities and load/save checks are required before any
waiver application; these candidates do not contribute to the table above.

### Next batch and admission efficiency

The queue successor has now completed: 641 independently admitted PASS VDBs in
`out/gap38-queue-current-20261004-02`. The predicted lane-3 MFPU-B line indices
120/121 and branch index 41 were hit. Whole-design raw gains were three line,
eight condition and two branch bits; ara_tb percentages remain unchanged at
two decimal places. The cumulative corpus retains all preceding 640 PASS VDBs.

The next compatible batch is being prepared from specific missing paths:
M-mode absent-feature CSR rejection, QBS generation/K-context faults and
preservation, AKV V1 legal skewed payload writes plus V2 recovery, and reachable
ordinary RVV operand/request paths. These are pending tests, not new coverage
or completed bug fixes. QBS generated byte routing is also being checked for
legal profile/address witnesses before selecting another short case. Do not
equate constrained physical buffer capacity with all currently missing byte
paths being unreachable.

The lane-3 conversion candidate is a single discriminating test, not a new
broad arithmetic sweep. Its first preparation was stopped before VCS because
the composition did not expand all sealed preflight manifests. The successor
`gap38-queue-current-20261004-02` uses `run_sealed_queue_extension.py`: exact
reconstruction of the original 298 file bindings and complete precheck result
is mandatory, and the bindings enter the frozen plan. Independent review,
seven replay-rejection tests and the real read-only replay passed. The source
and executable are unchanged. The subsequent VCS run passed in 135.22 seconds
and hit all three target bits. Lane-3 MFPU-B line coverage rose from 67.41% to
68.15%, and branch coverage from 70.21% to 70.64%. These are measured results;
the earlier preparation alone did not establish them.

The next compatible ready cases should be collected into one selection, with
up to eight workers and one final DVE export. In particular:

- CSR: M-mode access to missing H-owned addresses and RV64 high-half rejection
  paths, using distinct pure reads and necessary writes. S/U permission traps
  can mask the internal absent-feature guards. Preserve exception details,
  observable state, and legal recovery checks; avoid an indiscriminate
  instruction-form by privilege cross-product.
- Ordinary RVV: select remaining executable control and operand-delivery
  decisions from the latest completed corpus. Do not target inline observers,
  disabled configurations, or the already recorded carry/slide bugs merely
  to increase apparent coverage.
- QBS/AKV: distinguish missing legal payload/context combinations from unused
  physical storage bytes, unsupported descriptors, and unreachable fault
  sources before designing further short tests.
- FENCE.T: nonzero padding is a real branch target after a U-mode exit, but
  its independent cycle-level observer and prefix latency bound are not yet
  closed. Keep it deferred rather than launching a large-budget guess. The
  missing reset-only FSM arcs are not software stimulus targets.

A read-only admission cost review found 6.641 GiB of historical `row.files`
and approximately 22.69 GiB of logical hash reads in the baseline-related
parts of one prepare. These are file-size/call-model estimates, not measured
disk traffic or elapsed time. The highest-priority improvement is fewer
complete admission/aggregation rounds through batching. Keep independent
per-case checking and full phase-boundary integrity checks. Do not introduce
cross-run digest caches or trust timestamps as a substitute for file contents.

### Gap48 Checked Batch

`out/gap48-selection-20261004-01.json` composes five new cases on the complete
641-PASS corpus without changing any sealed case object. Preparation and VCS
results belong to `out/gap48-current-20261004-01`; use `./vstatus jobs gap48`
from the worktree root. A prepared selection is not a DUT PASS or a coverage
gain. Only the completed collection and native DVE report establish gains.

| Case | Discriminating behavior | Simulator budget |
| --- | --- | --- |
| csr_gap44_absent | M-mode absent-feature CSR traps and nonzero HPM preservation | 300 s |
| qbs_gap45_context | Generation/K mismatch, invalid context, preserved reuse and release | 600 s |
| akv_gap46_skew_context | Legal V1 halfword skew, cross-version invalidation and V2 recovery | 600 s |
| vgap47_sv39_indexed_pmp0 | S-mode ordered indexed load/store through Sv39, zero PMP entries | 300 s |
| qbs_gap49_payload_skew | Q5_K/Q8_K M1/N7/K1, legal W+2 skew across both weight banks | 600 s |

The batch registry accepts exact reviewed names only. The original gap47
nonzero-PMP assumption was rejected before VCS: this RTL has NrPMPEntries=0.
The replacement uses a zero-PMP Spike configuration and separates the DUT's
RAZ/WI PMP CSR interface from Spike's absent CSR interface. Old preflights
remain archived, never selected as current evidence.

The composition/runner has 21 passing unit tests and an independent review.
It verifies required original hashes, exact ordered case identities and the
selection's frozen hash before subprocess adapter dispatch. No RTL, frozen
checker or preceding outcome was changed for this batch. All five independent
prechecks passed during checked preparation. Final simulation results are four
PASS and one TIMEOUT (AKV); DVE and the final integrity checks completed. The
verified union now contains 645 PASS tests, excluding the timed-out VDB.

| Official raw DVE metric | 641 admitted | 645 admitted |
| --- | --- | --- |
| ara_tb line | 76.98% | 77.08% |
| ara_tb condition | 79.07% | 79.25% |
| ara_tb branch | 77.33% | 77.41% |
| ara_tb FSM | 53.44% | 53.44% |
| ara_tb toggle | 59.72% | 59.77% |
| CSR line | 47.90% | 58.64% |
| CSR condition | 40.81% | 43.08% |
| CSR branch | 34.03% | 43.61% |

Ordered incremental diagnostic gains are 144 line, 373 condition and 90 branch
bits. The absent-feature CSR test supplies 130/17/65, QBS context recovery
5/5/5, Sv39 indexed memory 9/9/4, and Q5_K skew 0/342/16 respectively. These
are genuine new hits without RTL changes or exclusions, not denominator
adjustments. Case ordering attributes shared hits only once.

### Bounded successors and reachability review

The AKV timeout is dominated by software checking: 144,887 of 223,178 retired
instructions regenerate source-byte expectations inside the comparison loop.
The four observed custom retirements occur at cycles 26,584, 101,272, 169,957
and 238,382. Completed phases show no mismatch, but no claim is made about
the unexecuted remainder. The successor computes expectations independently
once and uses full OR-of-XOR word comparisons. Do not enlarge the 600-second
limit, sample memory, refresh golden data from DUT output, or modify the old
frozen test. Fresh execution is mandatory.

The next QBS payload matrix targets 36 additional branch points across four
commands: Q5_K row-major M4/M3, Q2_K row-major M2/N8 and Q5_K interleaved M5.
The plan combines legal source skew, side metadata and bank/row routing;
all source bytes, destination register guards and architectural state remain
checked. Its predicted targets must be compared with the actual new VDB;
source-level reachability is not a measured coverage increment.

The next scalar proposal targets private ITLB/DTLB superpage slots and
ASID-selective SFENCE, with 7 line and 214 condition zeros identified. It uses
32 aliases for each of 2 MiB and 1 GiB mappings plus an observable 4 KiB remap.
Spike must validate all results with PMP0 and retire at most 45,000 instructions
before the 300-second VCS case is admitted. Do not demand stale translations
after an unrelated SFENCE: an implementation may legally over-flush.

Parameter reachability analysis separately identifies 1,144 candidate operand
queue branch vectors that demand TRUE from a statically FALSE support guard.
The 36-instance parameter/source/native-coordinate evidence is in
`out/gap53-operand-parameters-20261004-01`. It excludes the 16 already-reviewed
branch points and retains 1,269 other missing points for further investigation.
These are proposed exclusions, not applied waivers or new hits. Independent
review, current-corpus zero checks and a native DVE export/import validation
are required before any adjusted report can include them. Low coverage is
not itself a reason to waive a point.

### October 4 bounded successor evidence

In `out/gap55-current-20261004-03`, the new QBS and AKV tests both passed VCS
within their original 600-second bounds (368.03 and 370.89 seconds). The AKV
successor completed all 12 phases and 177 check groups, including three expected
illegal-command traps; its runtime audit records all nine planned line/branch
targets hit. It does not convert the old incomplete gap46 run into a PASS.
Official aggregate percentages are published only after DVE and final input
integrity verification, not by adding two to the previous test count.

Gap55 has now completed those checks and published the 647-test aggregate.

| Official raw DVE metric | 645 admitted | 647 admitted |
| --- | --- | --- |
| ara_tb line | 77.08% | 77.12% |
| ara_tb condition | 79.25% | 80.16% |
| ara_tb branch | 77.41% | 77.47% |
| ara_tb FSM | 53.44% | 53.44% |
| ara_tb toggle | 59.77% | 60.01% |
| QBS line | 98.39% | 98.54% |
| QBS condition | 75.22% | 78.37% |
| QBS branch | 95.03% | 95.27% |
| AKV line | 94.56% | 95.02% |
| AKV condition | 77.79% | 78.87% |
| AKV branch | 95.85% | 96.15% |

Ordered whole-case raw gains are 28/1,904/55 line/condition/branch bits for QBS
and 8/8/5 for AKV; neither changes FSM hits. All 36 preselected QBS payload
branches were checked against the pinned compile shape, baseline zeros and
fresh sample bytes and are now hit. The planned 36 plus AKV's nine target
points are subsets of these gains, not separate additions. No new waiver,
RTL change, or old-corpus simulation is responsible for the improvement.

The Sv39 successor's independent preflight and batch-adapter review passed.
Its actual Spike retirement count is 37,761, below the 45,000 admission bound.
It retains all 1,536 PTE, 1,024 data and 16 guard comparisons, five exact S-mode
trap records, and architectural state checks. The separate gap59 batch will
use a completed current corpus and a 300-second VCS limit.

The operand-queue reachability review independently accepted all 1,144 proposed
constant-FALSE guard vectors and retained the other 1,269 missing points. A
separate 18-point host-DVE pilot completed in 50.986 seconds: all selected
exclusions, 285 retained neighbors, empty-state checks and reset/import/export
identities were verified; input VDB hashes were unchanged. Evidence is in
`out/gap58-operand-native-pilot-20261004-02`. This qualifies only the observed
native format/session. It neither applies all 1,144 points nor changes the
official raw report. Full application still requires exact native identities,
current-corpus zero checks, independent review and a fresh bounded session.

### Current scalar and system boundaries

The completed-647 corpus is the input to the separately reviewed gap59 Sv39
batch. Checked preparation passed and the independent background service is
`ara-coverage-gap59-current-20261004-01.service`; `./vstatus jobs gap59` reports
progress. A running service or a passed Spike precheck is not a VCS result.

The read-only scalar review in `out/gap61-scalar-reachability-20261004-01`
classifies all 65 ALU line zeros and 61 ALU branch zeros as disabled-parameter
or producer-unreachable paths in the frozen configuration. It does not waive
them or declare functional ALU closure. Three compressed rejection paths
remain actionable: 0x8188, 0x9d4d and 0x9d61 with Zcb disabled. The planned
gap63 test checks three exact traps, preserved registers/memory and recovery;
its expected six line and three branch gains require actual VCS evidence.

The atomic review in `out/gap60-cache-atomic-analysis-20261004-01` establishes
a distinct integration limit, not an excuse to waive the A extension. The
frozen SoC contains an ATOP filter and an ordinary SRAM bridge, not an atomic
executor or exclusive monitor. RMW requests are rejected at L2; the current
AMO response interface contains only ack/result and does not propagate an AXI
error as an architectural AMO access fault. SC lock is not reservation-gated
by the SRAM bridge. These are source-derived risks/boundaries, not newly
measured failing traces or completed RTL repairs. Successful atomic RMW,
SC failure atomicity and LR/SC progress remain unverified. This image alone
cannot establish the atomic-memory capabilities required by a Linux system.

The bounded gap64 successor is deliberately LR-only: 24 LR.W/LR.D requests,
including signed word halves and preceding ordinary stores, with full data,
result and guard checks. Its oracle can establish returned read values and
completion, not reservations, SC behavior or concurrent aq/rl ordering.
The selected 25 line, 44 condition, 29 branch and five FSM diagnostic positions
remain predictions. Require a real PMP0 Spike precheck within 45,000 retired
instructions and keep the proposed VCS limit at 240 seconds. Batch this with
other reviewed new cases where practical, without re-running the old corpus.

Additional reviewed exclusions will be reported separately from raw hits.
Historical raw full-hierarchy export took about 185-198 seconds after test
selection. Cost the larger native verification session from those observations;
do not launch a three-export full report with an obviously insufficient
150-second DVE budget. Prefer one independently reviewed composite report to
duplicate CSR-only and queue-only full exports. No existing strict failed
gate or frozen exclusion policy is rewritten by this planning change.

## Completed Sv39 extension: 648 admitted tests

`out/gap59-current-20261004-01` is COMPLETE/PASS. The new VCS execution took
127.697 seconds, completed 110 architectural selfchecks, and passed the
unchanged independent directed audit. Report/ledger/bitmap hashes and exact
preservation of all 647 prior ledger rows were checked after publication.
No RTL, timeout, old checker, or coverage exclusion changed for this run.

| Official raw DVE metric | 647 admitted | 648 admitted |
| --- | --- | --- |
| ara_tb line | 77.12% | 77.12% |
| ara_tb condition | 80.16% | 80.26% |
| ara_tb branch | 77.47% | 77.47% |
| ara_tb FSM | 53.44% | 53.44% |
| ara_tb toggle | 60.01% | 60.18% |
| MMU subtree condition | 65.52% | 81.29% |
| ITLB condition | 71.25% | 93.33% |
| DTLB condition | 70.83% | 93.33% |
| Shared TLB branch | 89.19% | 91.89% |

The case adds five raw line, 220 condition and one branch positions, with no
new FSM positions. All 214 preselected condition positions are hit. Five of
seven planned line positions are hit; the two remaining ITLB/DTLB raw52
positions describe an empty type7 block at cva6_tlb.sv:298 whose statement has
line_ignore=1. They are not missing functional assignments and do not justify
repeating ASID patterns. No exclusion is inferred from this diagnostic label.

A supplemental read-only check of the actual VCS commit trace verified all
265 alias/remap sites (instruction, address, register/store value and masks)
and final reads of all 2,576 PTE/data/guard words. The trace has 22,072 retire
records and ends at cycle 61,392. These counts describe this DUT executable,
not the separately linked Spike runtime's 37,761 retired instructions.

### Next bounded work

The disabled-Zcb rejection test in `out/gap63-zcb-preflight-20261004-01`
has passed actual Spike execution: 82 checks and 13,898 retired instructions,
with Zcb disabled and PMP0. Parent replay also passed 82 compiled checker
negatives and 360 independent audit negatives. Its prospective VCS limit is
120 seconds; it is not yet admitted as an RTL PASS. Batch it with the separately
reviewed LR-only case when ready, then merge once with the completed corpus.

The QBS/AKV FSM audit in `out/gap62-custom-fsm-analysis-20261004-01` found
139/139 extracted state positions hit and 232/287 transition positions hit
across the selected engines. The main QBS and AKV engines already have all
their transitions hit. Remaining transitions concern shared-reader overlap,
compute faults and FP-slot reuse across reset. These diagnostic state/arc
counts must not replace DVE's arc-only percentages or become blanket waivers.
In particular, a reset-free impossibility proof does not establish global
unreachability when reset can retain a slot's state but clear its validity.

One new late-row QBS fault stimulus is under preparation, not yet launched:
M4/N5 with four valid rows followed by an invalid fifth-row address. Its
purpose is to exercise a fault during computation, not repeat the already
covered initial-load fault. Reserve the aliased SRAM tail and move the stack
before any C use; verify the memory map and independent fault/recovery oracle
before simulation. No claim of target coverage is made from preparation alone.

## Completed scalar/LR batch: 650 PASS

`out/gap67-current-20261004-01` is COMPLETE/PASS. Both new VCS executions,
their independent checks and the single DVE aggregation completed. The nine
published report hashes were independently checked; all 648 previous PASS
ledger rows remain identical, with exactly the two new names added. There
was no RTL/image rebuild, historical-test replay or new waiver application.

| Raw DVE metric, ara_tb | Previous 648 | Current 650 |
| --- | --- | --- |
| Line | 77.12% | 77.19% |
| Condition | 80.26% | 80.30% |
| Branch | 77.47% | 77.53% |
| FSM | 53.44% | 53.91% |
| Toggle | 60.18% | 60.21% |

| Added passing test | New line | New condition | New branch | New FSM |
| --- | ---: | ---: | ---: | ---: |
| scalar_gap63_zcb_reject | 6 | 0 | 3 | 0 |
| lr_gap64_wd_drain_pmp0 | 67 | 78 | 49 | 11 |
| Union relative to 648 | 73 | 78 | 52 | 11 |

The bit increments are diagnostic raw positions, not native score denominators.
The compressed decoder's line/branch scores rise from 54.35/51.16 to
59.42/54.65 percent. Commit-stage condition coverage rises from 72.22 to
87.04 percent. The AMO-buffer subtree's line/condition/branch scores rise
from 42.17/18.92/34.78 to 56.63/48.65/45.65 percent because LR uses this
path. This does not validate AMO RMW, SC, exclusive reservation success or
inter-hart ordering. Vector-backend, QBS and AKV scores are unchanged.

Zcb remains disabled: the new test checks rejection and precise recovery,
not Zcb implementation. LR.W sign extension and LR.D data are checked in
two phases with register, CSR and full guarded-buffer checks. The real Spike
trace's 45,000 retired instructions include a successful tohost write at
instruction 40,055 followed by 4,945 HTIF-wait self-jumps; it is not a
truncated run. CSR-restoration claims retain the test's documented masks and
harness boundaries, rather than claiming every exit CSR is unchanged.

The user requested completion of this batch and already-started preparation,
then a pause without expanding the campaign. The next late-row QBS fault case
and the composed native-waiver workflow are preparation only: neither belongs
to these 650 passing tests or to the scores above. The three-condition MMU
candidate from gap66 is deferred. Existing carry/slide failures remain open
and excluded; higher code coverage is not correctness or Linux signoff.

```bash
./vstatus jobs gap67
cat verification/out/gap67-current-20261004-01/checkpoint.json
```

### Prepared work retained for resumption

| Prepared item | Evidence | State at pause |
| --- | --- | --- |
| QBS late-row fault and numerical recovery | `out/gap65-late-fault-preflight-20261004-03` | 34 local tests pass; parent read-only admission check passes for 878 bound files. No RTL execution. |
| Composed native exclusion workflow | `out/operand-composite-review-20261004-01/incremental-review.md` | Focused review passes after capture-certificate semantic checks and bounded-run updates. No native capture or application. |
| PTW/MMU reachability analysis | `out/gap66-ptw-analysis-20261004-01/HANDOFF.md` | Analysis complete; optional three-condition test not constructed or launched. |

The QBS candidate retains the exact M4/N5 invalid-fifth-row case and M4/N4
recovery. A bounded read-only UCLI observer checks the actual compute-to-fault
transition and no premature architectural commit. Its Tcl command mocks and
host numerical checks do not prove the transition occurred on RTL. The
future standalone observer run is capped at 300 seconds, with no automatic
retry. It binds the completed 650-test baseline and the frozen image without
rehashing all historical VDBs on each diagnostic launch. Any later admission
into formal coverage still requires the normal checked collection workflow.

The exclusion workflow's 900-second total / 880-second DVE ceiling is an
agent-selected planning budget for a future bounded attempt, not an explicit
user-provided duration or permission to launch. No existing frozen policy is
changed. A future run still needs current-input validation, exact native point
qualification and a separate report-stage review. Its prepared 1345-point
union is not applied to the current raw scores and is not new stimulus coverage.

At the user's request, finish the existing batch and preparation only, then
pause. Resumption must be explicit; do not launch gap65, native exclusions or
new cases automatically from this handoff.

### Resumed QBS late-fault stimulus

The user subsequently resumed the prepared stimulus. Corrected runtime evidence
is `out/gap65-late-fault-runtime-20261004-02`: VCS passes 49 checks with zero
errors in 133.5 seconds. The observed cycles 6703/6704 prove the real
COMPUTE_TILE-to-FAULT_DRAIN transition while integer work is active. All
destination sentinels survive the fault, and all 16 numerical recovery outputs,
112 zero-tail words, CSR values and guards pass. The independent commit-trace
audit passes and raw FSM position 15 is newly hit.

Runtime01 remains a failed, excluded run with original sources archived. Its
only two failures were the boot-SP fixture's incorrect `0x80200000` expectation;
the frozen host simulation reports architectural DRAM end `0xc0000000`.
Only this new stimulus and its host fixture were corrected; no RTL, timeout,
numerical oracle, trap check or frozen image was changed.

A separate report-only audit handles the exact UCLI source-echo false alarm.
It removes exactly one byte-matched, pinned Tcl echo in memory and retains
actual failure detection, original logs and rejection records. All 35 stimulus
unit tests and 19 finalization tests pass. No failed VDB is relabeled or admitted.

`collect_gap65_observed.py` runs checked 650-case admission, one DVE export,
then checked aggregate finalization in that order under
`ara-gap65-coverage-20261004-02.service`. Check `./vstatus jobs gap65`.
Until COMPLETE is published, the formal aggregate remains the preceding
650 PASS. No native exclusion workflow or additional stimulus is launched.
