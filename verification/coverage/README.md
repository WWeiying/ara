# RTL Code Coverage: Current VCS/DVE Workflow

The active tool policy is host VCS plus DVE. Verilator and URG are not used.
The archived instructions below describe earlier work and must not be used to
launch a new campaign.

Current completed aggregate: 650 PASS tests, frozen image
`verification/out/repaired-aligned-build-20260930-01/sim/simv` and aggregate
`verification/out/gap67-current-20261004-01/combined-dve/summary.csv`.
Raw ara_tb coverage is line 77.19%, condition 80.30%, branch 77.53%, FSM 53.91%,
toggle 60.21%. These are neither functional coverage nor full signoff.

The prepared QBS late-row fault/recovery test has now passed VCS: 49 checks,
zero errors, 133.5 seconds. Its live observer and fresh VDB confirm the missing
COMPUTE_TILE-to-FAULT_DRAIN transition. RTL and the frozen image are unchanged.
The first run is retained and excluded: its test fixture incorrectly expected
the FPGA/Spike initial SP instead of the VCS architectural DRAM-end SP.
Report-only recovery also distinguishes exact UCLI source echo from actual
failure output; original logs and the postprocessing rejection are preserved.
Checked aggregate admission and DVE export use the independent runtime directory
`out/gap65-late-fault-runtime-20261004-02`. The published count remains 650
until its collection reaches COMPLETE. Check `./vstatus jobs gap65`; use
`./vstatus jobs gap67` for the preceding completed aggregate. Future checked
extensions from the new aggregate must install the narrowly scoped admission
hook in `finalize_gap65_observed.py`; ordinary baseline checks are unchanged.

The latest disabled-Zcb and LR-only extension passed both VCS tests and their
independent admission checks. All 648 preceding PASS ledger rows are unchanged;
the two new tests add 73 line, 78 condition, 52 branch and 11 FSM raw positions.
These diagnostic bit counts are not DVE percentage denominators. No new waiver
was applied, no RTL was modified, and the preceding tests were not rerun.
LR.W/LR.D checks do not establish SC, AMO RMW, reservation or memory-ordering
correctness. Use `./vstatus jobs gap67` from the verification worktree.

The preceding Sv39 extension passed in 127.7 seconds without rebuilding the image
or rerunning the prior 647 tests. All 214 planned conditional points hit;
ITLB and DTLB condition coverage are now both 93.33%. The completed aggregate
preserves every prior PASS ledger row unchanged. RTL carry/slide issues and
the atomic-memory integration limits remain open; this result is not Linux
system signoff.

`run_checked_extension.py` wraps the frozen `run_targeted_extension.py` and
supports new directed cases without rebuilding RTL or repeating the old
corpus. It additionally checks historical independent PASS evidence and binds
the new test prechecks to the exact ELF/source/log hashes. Native Spike
prechecks and host-only custom-operation references are distinguished; a host
reference PASS is not a custom-instruction execution PASS. Unsupported
precheck formats fail closed. A selection manifest names the audited
baseline, its raw bitmap cache, new ELF/source/precheck evidence, a bounded
timeout and the actual RTL hierarchy targets. The established self-check and
independent audit must both pass before admission. Up to eight simulations run
concurrently, with one DVE export after the batch.

The report contains the full passing ledger, raw and hierarchical DVE
increments, and per-case raw bitmap gains. Diagnostic bitmap counts must not
be presented as DVE percentage denominators. An incompatible simulator,
changed source/checker, truncated VDB or failed audit stops the affected queue.
Ordinary functional failures are retained and excluded from verified coverage.

```bash
python3 verification/coverage/run_checked_extension.py --output verification/out/NEW_RUN --selection SELECTION.json --prepare
python3 verification/coverage/run_checked_extension.py --output verification/out/NEW_RUN --launch
cat verification/out/NEW_RUN/checkpoint.json
cat verification/out/NEW_RUN/collection.json
```

The completed ten-case extension is
`verification/out/gap35-vector-checked-preflight-20261004-03`. Despite the
historical directory label, this prepared directory was subsequently launched
as a real VCS campaign. Five new PASS VDBs join the old 625. Two functional
FAILs and three TIMEOUTs are excluded. The same-ELF CSR permission retry passed
with its measured 300-second budget; its earlier incomplete VDB remains
excluded. The QBS wide-row/tail test accounts for 36 new raw FSM positions;
official QBS compute-engine FSM coverage increased from 60.09% to 76.23%.

`run_fence_checked_extension.py` adds narrowly scoped admission for the real
CVA6 FENCE.T instruction, which standard Spike cannot validate. Its precheck
is explicitly static ELF validation, not a model or hardware PASS. After VCS,
admission additionally requires the exact two retired fence/resume sequences,
458 architectural selfchecks, and native controller transition-arm/FSM
activity. A UART PASS alone is insufficient. It wraps the same frozen runner
without changing RTL, the simulator, or historical results. Use the same
`--prepare`/`--launch` interface and a new output directory.

The first FENCE.T VCS run in
`out/gap36-fence-current-20261004-02` printed all 458 checks passing, but its
commit audit rejected repeated PC+4/PC+8 records (`duplicate resume`). It is
NOT admitted. Keep its VDB for diagnosis only; do not bypass the extra audit
or classify the trace anomaly as a proven RTL defect without tracing its
source.
The read-only diagnosis in `out/gap36-fence-diagnosis-20261004-01` correlates
RVFI, ELF and cycle-stamped logs: stale legacy tracer identities label later
stores as repeated resume instructions. RVFI shows single retirement and
correct capture data. The original rejection remains; no duplicate filtering
or new coverage admission has been performed.

The new `run_fence_rvfi_checked_extension.py` uses a separately frozen
admission contract. It checks every RVFI retirement opcode against the linked
ELF, the unique straight-line resume sequences, all 130 GPR/FPR/PC capture
stores, and the absence of FENCE register/memory side effects. The original
UART checks and native controller transition requirements remain mandatory.
The legacy trace is retained as diagnostic evidence, not filtered into an
oracle. Replaying old logs in unit tests does not admit the old rejected VDB;
a fresh VCS execution is required. This wrapper also accepts the separately
reviewed `gap37_csr_admission.py` contract for SIE aliases and SATP/TVM access.
That CSR test's full probe stream is checked on Spike; on VCS its immutable
626-check program, exact completion summary and existing independent directed
trace audit must pass. Do not claim a per-phase RVFI CSR oracle from this test.

`run_reviewed_dve_20261004.py` is a separate report-only entry point for the
current frozen design. It reapplies only the 94 exact points and 10 observer
instances re-audited in `reviewed_20261004`. It verifies source and shape
identities, the admitted corpus, and that the supposedly unreachable points
still have no hits. It snapshots the existing exporter without editing old
collectors or VDBs. Native saved exclusions must match the reviewed checksums
and signatures exactly, and the raw report must remain unchanged.

```bash
PYTHONPATH=verification python3 verification/coverage/run_reviewed_dve_20261004.py \
  verification/out/NEW_REVIEWED_REPORT \
  --baseline verification/out/gap35-vector-checked-preflight-20261004-03
```

Only `waiver_status.json: APPLIED` with successful process completion confirms
application. `PREPARED` is not an adjusted result. Compare `summary.csv` and
`summary_waived.csv` side by side; waiver gains are not new test coverage.
New inline `FOR_VERIFY` point candidates are deliberately not included.
The first current-image application completed in
`out/dve-reviewed-630-20261004-01`: exact 94 points plus 10 observers, with
all raw hierarchy rows unchanged. Adjusted ara_tb line/condition/branch/FSM/
toggle coverage is 76.85/79.04/77.28/52.96/60.61 percent. The line decrease
reflects removal of highly covered observer code, not a failed test.

See [COVERAGE_CLOSURE_PLAN.md](COVERAGE_CLOSURE_PLAN.md) for closure criteria.
Only reviewed exclusions bound to the exact design/shape may be applied;
raw measurements must remain available for comparison.

The completed eight-case bounded timeout-successor batch is registered in the
existing read-only status helper (from the verification worktree):

```bash
./vstatus status gap36-8
./vstatus jobs gap36-8
cat verification/out/gap36-timeout-current-20261004-01/checkpoint.json
```

All eight new cases passed and join the 630-PASS baseline, without replaying
those 630 tests. QBS descriptor-decoder branch coverage rose from 37.04% to
81.48%; AKV condition coverage rose from 73.62% to 77.79%. The previous carry
restart and slide prefix failures remain excluded and unresolved.
`RUNNING` may include source/evidence validation before workers start; consult
`simulations_started` and the scheduler rows before claiming simulations are
executing. New percentages require a completed, admitted DVE report.

The completed two-case control extension is registered as `gap37-control`;
its successful report-only finalizer is `gap37-finalize`:

```bash
./vstatus status gap37-finalize
./vstatus jobs gap37-finalize
tail -n 10 verification/out/gap37-control-current-20261004-01/logs/json-finalization.log
```

Both fresh VCS cases and their extra audits passed. Controller branch coverage
rose from 50.00% to 65.52%, FSM from 0.00% to 62.50%; CSR branch coverage rose
from 32.75% to 34.03%. The previous 638 tests were not rerun, and the rejected
old FENCE VDB remains excluded.

The original service stopped after simulation because the FENCE proof's two
65-entry dictionaries used integer offset keys in memory and string keys in
JSON. `finalize_gap37_control.py` reconstructs the original proof and permits
only that exact key conversion. All values, other fields, files and VDB hashes
must match. It archives the original STOPPED checkpoint and invokes the
unchanged checked exporter. Independent review and negative tests passed;
the final checkpoint/collection are PASS, COMPLETE, 640. No original checker,
worker result or VDB was modified. The old service's failed status is retained
as history, not a new simulation failure.

The completed queue candidate is `vgap38_i8_f16_lane3`, with 1,274 Spike selfchecks
and a separate 512-input host validation of its integer-to-binary16 oracle.
`prepare_gap38_queue_batch.py` requires the exact lane-3 MFPU-B target bits to
remain missing in the completed successor corpus before composing a selection.
The ordinary checked runner still performs full admission. Spike PASS and a
prepared selection are not DUT PASS or evidence of a coverage increment.

The queue successor uses `run_sealed_queue_extension.py`. It also expands
the preflight tool, link-input, protected-input and artifact hash manifests;
reconstructs exactly the 298 original file bindings; and compares the entire
precheck result with the sealed record. All bindings then enter the ordinary
frozen plan. Real read-only replay, seven positive/negative tests and independent
review passed. The first prepare directory (`gap38-queue-current-20261004-01`)
was stopped before VCS to add this guard and has no simulation results.
The successor is `gap38-queue-current-20261004-02`; source and ELF are unchanged.
Its VCS run and independent admission passed, and the final collection contains
641 PASS VDBs. All three predicted lane-3 MFPU-B targets were hit: two line
points and one branch point. Across the design it added three line, eight
condition and two branch raw bits. Raw ara_tb percentages round to the same
two-decimal values as the 640-test report; this is not a zero-gain test.

`verification/tests/compose_gap48_selection.py` combines ready case drafts on
one completed corpus. It rejects duplicate names/ELFs, missing independent
prechecks and budgets over 600 seconds. Composition does not approve a case:
each case's sealed preflight and the full checked runner admission must still
pass. Batch-ready compatible cases should share one prepare and one DVE export,
with at most eight active VCS workers and no replay of the historical corpus.

The five-case successor is `out/gap48-current-20261004-01`: absent-feature
CSR rejection, QBS context faults/recovery, AKV skew/context recovery, PMP0
Sv39 indexed memory and Q5_K skewed payload routing. All five independent
prechecks and full 641-PASS baseline admission passed. Four new cases passed;
the AKV case reached its 600-second limit and is excluded. The final status is
`COMPLETE_WITH_FAILURES`, coverage is `COMPLETE`, and the verified aggregate
contains 645 PASS VDBs. This status does not mean DVE failed. The batch adds
144 line, 373 condition and 90 branch raw diagnostic points, with no new FSM
points. CSR line/branch coverage increased from 47.90/34.03 to 58.64/43.61
percent; these are official DVE values, not a waiver adjustment.

The AKV timeout trace contains 223,178 valid retired instructions; 144,887
(64.92%) execute the repeated source-regeneration comparison loop. Four custom
commands retired and no incorrect result was observed in the completed
phases, but the remaining commands and checks are unverified. Preserve this
TIMEOUT and its VDB as diagnostic-only evidence. A new `akv_gap54_skew_context`
case computes independent expected source bytes once and retains complete
comparison through aggregate word checks. It must pass separate admission
and fresh VCS execution before contributing coverage.

`run_gap55_sealed_batch.py` is the next independent batch entry point for
`qbs_gap51_payload_matrix` and `akv_gap54_skew_context`. It reuses and pins the
sealed gap48 admission code, accepts only those exact names, and does not
change historical outcomes or rerun the 645-test corpus. Prepared tests are
not yet DUT PASS. Use the same compose/prepare/launch sequence once both
independent preflights and the batch review are complete.
The original prepared directory `gap55-current-20261004-01` was stopped before
launch: the first adapter did not consume the AKV seal's exact result/file-set
contract. The supplementary `run_gap54_akv_sealed_extension.py` checks the
original selection, seal hash, draft hash, complete case hash and replayed
result/file set, without rebuilding the ELF or editing the old preflight.
The second prepare was stopped before checked admission to reject missing or
malformed mandatory seal/draft digests. Both rejected preparations contribute
no VDB; the original app ELF and software preflight remain unchanged.
The final candidate directory is `gap55-current-20261004-03`;
`./vstatus jobs gap55` tracks it. The supplementary gate has 19 passing tests,
including mandatory-digest, result, file-set and composition failure cases.

Both new tests have now passed VCS: QBS in 368.03 seconds and AKV in 370.89
seconds. The AKV runtime audit verifies all 12 command phases, 177 check groups,
three expected traps and all nine targeted native line/branch points. The old
gap46 TIMEOUT remains unchanged and excluded. These completed outcomes are not
substitutes for the original timeout. Gap55's DVE and final integrity checks
have completed; its official aggregate contains all 647 PASS tests. Diagnostic
new hits are 36 line, 1,912 condition and 60 branch bits, with no new FSM bits.
The QBS case hit all 36 preselected payload branches (24 in bank0, 12 in bank1).
These target hits are a subset of the whole-case gains, not additional counts.

`run_gap59_system_batch.py` admits only the separately reviewed
`sv39_gap52_superpage_sfence_pmp0` successor. Its sealed Spike trace has 37,761
retirements, 110 checks, 64 alias hops, 74 selective fences, five S ecalls and
all 2,576 table/data/guard words checked. Independent review and 26 case tests
plus five wrapper tests passed. Compose on the newest completed raw corpus,
preserve the sealed case object and retain the 300-second VCS bound. This
preflight result is not a DUT PASS or a measured coverage increment.
`./vstatus jobs gap59` tracks this next batch, composed on the completed 647-test
gap55 corpus. It never reruns the original 647 tests.

```bash
./vstatus jobs gap38-prepare
./vstatus status gap38-queue
./vstatus jobs gap38-queue
./vstatus jobs gap48
./vstatus status gap55
./vstatus jobs gap59
```

# Archived Verilator Workflow (Inactive)

## Staged collection

Do not rebuild and replay the full matrix after every RTL bug fix:

1. During debugging, use the frozen VCS/Spike ELF and its independent audit to
   run only the failing directed case and one nearby regression. Do not
   collect whole-design coverage for each candidate.
2. At an RTL checkpoint, build one incremental Verilator image and run a small
   representative set. Save each passing case's `result.json` and review the
   uncovered points in the changed modules. Add only cases that exercise a
   specific gap; do not repeat previously passing cases on the same image.
3. At RTL freeze, run the complete audited directed/random and real-kernel
   matrix once. Merge all passing cases from that exact simulator hash. If a
   new case is added without changing RTL, run only that case and re-merge the
   old and new `result.json` files. Do toggle collection only for the
   state/control blocks where line and expression coverage leave a question.

The build directory supports incremental C++ compilation. Frozen source ELFs
and VCS/Spike audits survive RTL changes, but Verilator `coverage.dat` does
not: a changed simulator hash requires a new coverage run for any case used
in the final aggregate. This is a measurement constraint, not a reason to
rerun every case after each intermediate fix.

For the current final-source checkpoint, after its coverage build service has
completed successfully, `run_final_stage1.sh` replays five audited directed
edge cases, one audited seed from each of six random profiles, and one QBS/AKV
functional smoke on the same image. It merges and independently audits the 12
result files, then writes an uncovered-point review. This is a diagnostic
checkpoint, not full-matrix signoff. The initial `-01` run stopped at its old
600-second wall-clock limit; a longer retry subsequently exposed missing
tohost termination in the C++ harness. The corrected image is being checked
with one frozen random ELF before expanding the matrix. Failed artifacts
are retained, including `failed_memory101_600s`. The current per-case limit
is 3,600 seconds. After that preflight passes, reuse it in stage 1:

```bash
ARA_COVERAGE_REUSE_AUDIT="$PWD/verification/out/integrated-tohost-coverage-preflight-20260925-01/merged/audit.json" \
  bash verification/coverage/run_final_stage1.sh \
  "$PWD/verification/out/integrated-final-stage1-20260925-02"
```

After stage 1 passes and its missed-point review is inspected,
`run_final_stage2.sh` replays only the remaining 64 independently audited
random cases: four more in the first memory-cross batch, all 15 in the other
three memory-cross batches, and nine more per remaining profile. Each
simulation is capped at 3,600 seconds, with four cases per batch running in
parallel. The script requires the exact stage-1 simulator hash, then extends
its audited merge to 76 cases instead of rerunning the first 12:

```bash
bash verification/coverage/run_final_stage2.sh \
  "$PWD/verification/out/integrated-final-stage2-20260925-01"
```

This command is prepared but must not be treated as completed coverage until
its new case results, merged integrity audit, and missed-point review pass.
It is resumable in the same output directory after an interrupted batch: the
script verifies the simulator, source-manifest, summary and source-audit hashes,
reuses only passing case artifacts from that image, and sends missing cases to
a new `retry_N` subdirectory. It preserves failed artifacts for diagnosis and
refuses a changed image or input instead of combining incompatible coverage.
An interrupted directory without provenance is not reused; only its missing
cases are replayed in a new subdirectory. A recorded failing case stops the
stage for diagnosis rather than being retried automatically.
The 76-case report step has a separate 600-second timeout. If it stops before
writing an audit, the partial merge is retained as `merge_incomplete_N` and
the next invocation rebuilds only the report from the passing case files.
`ARA_COVERAGE_STAGE1` selects a different completed stage-1 directory.
`ARA_COVERAGE_SOURCE_MANIFEST` selects its matching source manifest for either
stage. Both default to the tohost-corrected checkpoint; the scripts still
check the source manifest and exact executable identity.

The general directed/random runner also accepts `--reuse-audit OLD/audit.json`.
It re-audits all retained files, rejects another simulator image, and matches
the frozen ELF hash and tohost address. Only unmatched cases are simulated;
`case_replay.json` records `reused: true` and the original result path for
each reused case. A timeout or failed test never qualifies for reuse.

For a same-image addition, point to the previous audited merge and pass only
new results. The command re-audits old artifacts, verifies every input hash,
rejects duplicate cases or mixed images, and inherits the original coverage
scope:

```bash
python3 verification/coverage/merge_verilator_coverage.py \
  --extend-audit verification/out/checkpoint/merged/audit.json \
  --case verification/out/new-case/result.json \
  --output verification/out/checkpoint-plus-new \
  --verilator-coverage install/verilator/bin/verilator_coverage
```

Run `audit_merged.py` and `review_uncovered.py` on the new output as usual.

The repository-local Verilator 5.038 can collect RTL code coverage from tests
that actually run on its instrumented Ara image. It cannot read VCS `.vdb`
files. Keep functional signoff (VCS/Spike and in-program checks) separate from
coverage collection; a generated `.dat` file alone is not a passing test.

An independently audited VCS/Spike random batch can be replayed on the same
instrumented image as directed tests. The runner re-audits the frozen source
batch with complete vector/full-match requirements, checks each ELF hash, and
requires the program's success marker again in Verilator:

```bash
python3 verification/coverage/run_directed_coverage.py \
  --random-source \
  --summary verification/out/integrated-wred-m8-memory101-replay-20260925-01/summary.json \
  --audit verification/out/integrated-wred-m8-memory101-replay-20260925-01/independent_audit.json \
  --simv verification/out/integrated-verilator-coverage-20260925-01/build/verilator/Vara_tb_verilator \
  --source-manifest verification/out/integrated-verilator-coverage-20260925-01/source_manifest_tohost.json \
  --ram-bytes 2097152 --jobs 2 --term-cycles 250000 --timeout 3600 \
  --output verification/out/integrated-wred-m8-memory101-coverage-20260925-01
```

The 250,000-cycle value is a ceiling, not a target duration. Some audited
random cases finish after 100,000 cycles; using a lower blanket ceiling can
turn a valid regression into a false timeout.
Random replay obtains `+COMMIT_TOHOST` from the audited VCS command JSON and
passes it to the C++ monitor. For a direct single-ELF invocation, specify
`run_verilator_coverage.py --tohost-addr 0x...` using that ELF's tohost symbol.
The address is checked for alignment and compiled RAM bounds. Ordinary Ara
apps retain the control-register exit path. Both paths must produce the
exact success marker; hitting a cycle or wall limit is never PASS.

Use a distinct output directory for each seed batch. Merge only PASS results
from the same `simv_sha256`; the resulting coverage numbers describe that RTL
image and may not be carried forward after RTL changes.

Build once in an independent output directory:

```bash
make -C hardware verilate \
  buildpath="$PWD/verification/out/verilator-coverage-current/build" \
  qbs=1 akv=1 akv_v2=1 veril_coverage=1 veril_jobs=8
```

`veril_coverage=1` enables line and expression coverage. Set
`veril_coverage_toggle=1` only for a separately budgeted toggle run; it can
increase model size substantially. The default Verilator build remains
uninstrumented. Repeating the same command keeps the generated C++ and object
files under `build/verilator`; Verilator checks RTL changes and `make` rebuilds
changed objects. RTL or Verilator option changes regenerate the model in the
same directory, so unchanged C++ objects can be reused. Changes to C++
compile options invalidate the old objects; `veril_clean=1` forces a full
rebuild. Keep separate `buildpath` values for
simultaneous builds; do not run two builds in the same directory concurrently.
The C++ testbench writes `coverage.dat` at normal simulation
completion; pass `+verilator+coverage+file+<absolute-path>` to isolate cases.

While the build runs, freeze its source inventory and recheck it after the
binary is complete. This hashes the Bender filelist, selected RTL, include
headers, Verilator testbench sources and build configuration:

```bash
python3 verification/coverage/build_provenance.py \
  --filelist verification/out/verilator-coverage-current/build/verilator/bender_script_default \
  --repo-root . --build-dir verification/out/verilator-coverage-current/build/verilator \
  --output verification/out/verilator-coverage-current/source_manifest.json
python3 verification/coverage/build_provenance.py \
  --output verification/out/verilator-coverage-current/source_manifest.json --check
```

Run a previously validated ELF and require its own PASS marker:

```bash
python3 verification/coverage/run_verilator_coverage.py \
  --simv verification/out/verilator-coverage-current/build/verilator/Vara_tb_verilator \
  --elf apps/bin/llama_qwen25_q4_0_decode_attn_q_rvv \
  --output verification/out/verilator-coverage-current/rvv-q4-0 \
  --verilator-coverage install/verilator/bin/verilator_coverage \
  --term-cycles 2000000 --timeout 900
```

The runner first copies the simulator and ELF into each case directory and
checks both copies against their source hashes; execution uses only those
frozen copies. It saves their hashes, simulation command and log,
`coverage.dat`, LCOV `coverage.info`, and `result.json`. A case is `PASS` only
when the simulator exits successfully, the program prints its success marker,
and the coverage report is nonempty. Raw line/branch counts include testbench
and dependency code; a DUT-only percentage requires an explicit hierarchy or
source-scope filter, exclusions, and review of uncovered points. Verilator's
expression/branch metrics are not identical to VCS condition/FSM coverage.
On timeout or self-check failure, `result.json` records elapsed time, the
simulation-log hash and its last lines; an existing partial `coverage.dat` is
hashed for diagnosis but remains ineligible for merging.

Merge only passing cases from the **same simulator hash**:

```bash
python3 verification/coverage/merge_verilator_coverage.py \
  --case case-a/result.json --case case-b/result.json \
  --output merged-coverage \
  --verilator-coverage install/verilator/bin/verilator_coverage \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/
```

The merge rejects failed cases, changed simulator/ELF/log/coverage inputs, and
mixed simulator hashes. Its raw-point DUT
count uses Verilator's instance hierarchy and fails when that hierarchy has no
points. `audit.json` reports per-source and per-type counts after both the
hierarchy and source filters; `uncovered.jsonl` retains every missed point with
its source line, type, instance, and label for review. The LCOV source-path
view is separate and may count other instances of the same module. Neither
view by itself closes unreachable points or configuration-specific targets.

After a merge, independently re-audit the frozen cases and merged files:

```bash
python3 verification/coverage/audit_merged.py \
  --audit merged-coverage/audit.json --minimum-cases 3 \
  --report merged-coverage/integrity_audit.json
```

This verifies simulator/ELF/log/coverage hashes, a common image, merged
line/expression counts and the exact missed-point list. Its `PASS` means the
collection is internally consistent; it does **not** mean the missed points
have been justified or a DUT coverage target has been met.

The same integrity check can be recorded as a separate signoff gate:

```bash
python3 verification/run_signoff.py --stage coverage-integrity \
  --coverage-merge-audit merged-coverage/audit.json \
  --coverage-minimum-cases 3 --output signoff-coverage-integrity
```

The gate refuses a missing or altered merge, but a `PASS` here is only
collection integrity. Review `uncovered.jsonl` and document justified
exclusions separately before claiming DUT code-coverage closure.

For a ranked DUT/source gap summary after integrity checking, run:

```bash
python3 verification/coverage/review_uncovered.py \
  --audit merged-coverage/audit.json --minimum-cases 3 \
  --output merged-coverage/review.json
```

`review.json` groups missed points by source, coverage type and line. Its
`REVIEW_REQUIRED` status deliberately does not claim coverage closure; each
large gap still needs a stimulus, configuration or reachability assessment.

For a separately collected toggle image, run the same integrity audit before
listing control signals worth reviewing:

```bash
python3 verification/coverage/review_toggle_signals.py \
  --audit toggle-merged/audit.json --minimum-cases 2 \
  --pattern 'state|valid|ready|pending|credit|exception|fault|full|empty|ack|grant' \
  --output toggle-merged/watched_toggle_signals.json
```

The output groups bit-level points by RTL signal and lists bits with at least
one reported toggle. It does not prove both transition directions, protocol
coverage, or functional correctness. Compare it with the audited passing
cases and inspect the missed control bits individually. Toggle and
line/expression images may be merged only within their own image hashes, not
with each other.

The standalone `verilator_coverage_smoke.sv` proved the local Verilator and
LCOV export path. It is a tool smoke, not an Ara coverage measurement.

For the frozen Q4_0 RVV/QBS ELFs and the previously passing AKV-v2 column
smoke, place the three files under `OUTPUT_ROOT/inputs/` with their original
names, then run the
matrix on one completed instrumented image:

The matrix checks each ELF's `PT_LOAD` physical-address range and 16-byte
load alignment against the 1 MiB, 4-lane Verilator RAM before simulation and
saves `elf_fit.json`. File size
alone does not establish that an ELF fits; the original AKV-v2 full-model
ELF crossed the RAM boundary even though the file was only about 2 MiB.

```bash
bash verification/coverage/run_representative_matrix.sh \
  verification/out/verilator-coverage-vstu-fixed-20260924-01 \
  verification/out/verilator-coverage-vstu-fixed-20260924-01/build/verilator/Vara_tb_verilator
```

The runner checks `representative_inputs.sha256` before executing the three
self-checking ELFs sequentially, then merges only
their PASS coverage files, and writes `merged/integrity_audit.json`. It never
reuses a prior case output. Inspect `merged/uncovered.jsonl` and document
justified exclusions before treating the DUT coverage as closed.
