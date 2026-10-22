# DVE coverage automation

Reviewed waivers are now applied automatically to matching compiled designs.
The original `summary.csv` remains raw; `summary_waived.csv` is a separate DVE
result and `exclusions.el` is the native reusable exclusion file. Check
`waiver_status.json` for `APPLIED`; an unknown design is not automatically
waived. See [DVE waiver policy](DVE_WAIVERS.md). Use `DVE_WAIVERS=off` for a
raw-only export. Existing historical reports are not rewritten.

## Validation worktree

The active copy is in `/home/wangwy/openproject/ara_dsa_signoff_integration`.
Run this copy from the validation worktree; do not write campaign outputs into
the product worktree. The source wrapper, Tcl exporter, and host tests were
migrated together from `ara_dsa` without changing coverage selection semantics.

For a new current-RTL campaign, compile with `code_coverage=1` into a new
build/simulation directory. Run each test with
`-cm line+cond+fsm+tgl+branch -cm_dir /absolute/case/code.vdb -cm_name CASE`.
Archive the compile command, RTL/filelist hashes, simulator identity, ELF,
test command and independently checked result. Only matching, completed PASS
test VDBs belong in the verified report. A historical PASS without a test VDB
cannot be converted into coverage; it must be rerun on the instrumented image.

Keep the compile VDB and every original test VDB. DVE summary percentages are
not raw covered/total bin counts; unreported metrics remain NA. No assertion
coverage is claimed by the current `line+cond+fsm+tgl+branch` configuration.
The obsolete Verilator percentages must not be combined with these reports.

This workflow uses DVE V-2023.12-SP1 in a virtual X display. It does not call
URG and does not require a visible desktop or manual interaction. It still
uses the DVE GUI engine and requires a working DVE license.

From the repository root:

```bash
bash verification/coverage/run_dve_coverage.sh \
  /tmp/dve-coverage-report /absolute/path/to/simv.vdb
```

For a compile database plus separate test databases, pass all paths after the
output directory. The first input must contain the compiled design. They must
originate from compatible instrumented builds; matching VCS version alone does
not establish compatibility. The exporter enumerates testdata directories and
explicitly selects all tests using `gui_open_cov -test ... -merge MergedTest`.
DVE performs the coverage-point merge. Simply passing several databases with
`-dir` was found to select only the first test in this installation.

The output directory must not already exist. Outputs:

- `summary.csv`: names, tree depth and the coverage columns displayed by DVE.
- `inputs.txt`: absolute input database paths.
- `selected_tests.txt`: the explicit test selection passed to DVE.
- `rejected_tests.txt`: incomplete test directories, when validation fails.
- `diagnostics.txt`: warning/error diagnostics that invalidate the export.
- `launcher.log`: process startup diagnostics.
- `xvfb.log`: virtual X server diagnostics.
- `DVEfiles/dve_gui.log`: Tcl output and the export completion marker.

The script queries `gui_list_get_property` and `gui_list_get` on the loaded
coverage summary table and preserves DVE's displayed percentages. Blank
cells are `NA`, not zero. The export is the summary tree populated by DVE,
not a guarantee of exhaustive DUT hierarchy or uncovered-bin enumeration.
Displayed percentages are rounded; the `Score` column is DVE's aggregate
score, not a user-computed ratio of all covered points to all coverable points.
Do not add parent and child percentages or substitute this summary for
coverage signoff, exclusion review or build provenance checks.

The default timeout is 180 seconds. Override it with
`DVE_COVERAGE_TIMEOUT=600` for a large database. An unsuccessful export retains
its logs and, if created, `summary.csv.partial`. Check the command exit status;
files left by a failed run must not be treated as a valid report.
Only the shell wrapper publishes `summary.csv`, after checking the process
status, Tcl completion marker and DVE diagnostics. Until then, data remains
in `summary.csv.partial`. Any Warning/Error/Fatal diagnostic in the launcher
or DVE GUI log is rejected conservatively, including database mismatches and
coverage data that DVE refuses to merge. Investigate benign warnings rather
than treating a partially merged report as successful.

Input directories must end in `.vdb`; duplicate database paths are rejected.
Every testdata directory must contain readable, nonempty `*.data.xml` files;
an incomplete directory invalidates the entire report and is listed in
`rejected_tests.txt`. This does not prove simulation completion or XML/build
compatibility; PASS status and build provenance still require independent
checks. Input-list files can use LF or CRLF line endings. The output directory
is claimed atomically and must be outside all input VDBs. Timeout handling
signals the tool process group and forces termination after a ten-second
grace period. `DVE_COVERAGE_TIMEOUT` must be positive integer seconds.

`-nogui` is deliberately not used: the installed DVE wrapper routes that
option to `ucli.exe`, which does not accept `-cov`. `gui_window_dump` was also
tested but did not export the coverage cells in this installation.

The exporter was smoke-tested with an existing small `host_debug_tb` VDB:
Line 95.80%, Toggle 4.22%, Condition 69.90%, Branch 85.71%, Score 63.91%.
These are automation test results, not Ara coverage results. A pre-existing
output directory is rejected. The Tcl uses arrays rather than `dict` because
the embedded interpreter in this DVE installation does not support `dict`.

## Repeated tests

`simv.vdb` is a directory containing the compiled coverage definition, not a
CSV report. Keep each completed run's `code.vdb` separately. A report combines
coverage points across the selected tests; do not average or concatenate
per-test CSV percentages to calculate cumulative coverage.

For a small set:

```bash
bash verification/coverage/run_dve_coverage.sh /tmp/dve-merged \
  /build/simv.vdb /runs/case1/code.vdb /runs/case2/code.vdb
```

For many runs, put the design VDB first and one test VDB path per subsequent
line in an input text file, then use:

```bash
bash verification/coverage/run_dve_coverage.sh /tmp/dve-merged-next \
  --inputs-file /path/to/vdbs.txt
```

Adding a run means updating this input list and exporting into a new output
directory. This recomputes the cumulative view from retained VDBs; it does not
rerun simulation or save a new merged VDB. Keep the original databases.
Use only completed, independently checked passing cases for a verified
coverage report. Keep failed or timed-out cases in a separate exploration
report. The exporter rejects test inputs without coverage data, but does not
automatically inspect case PASS records or prove build compatibility.

An actual Ara VDB was successfully exported from
`ara_dsa_verification/verification/out/code-coverage-vadd-20260923-01`, using
its compile VDB and `tests/rvv_vadd/work/code.vdb`. The case record is PASS.
DVE's `ara_tb` row reports Line 41.69%, Toggle 14.22%, FSM 5.86%, Condition
37.91%, Branch 38.33%. These are the older build's testbench-top aggregates,
not current integration-branch coverage or a DUT-only signoff result.
The neighboring `code-coverage-rvv-context-20260923-02` run timed out and its
test VDB contains only an empty `.mode64`; the exporter rejects that input.

The explicit multi-test selection was tested separately on a small
`merge_smoke` design compiled once and run with two input modes. Single-test
Condition/Branch were 50.00%/50.00%; merging both tests produced
100.00%/75.00%. `selected_tests.txt` contained both test identities. This
checks merge functionality, not Ara coverage. The input-list option was also
tested, and all temporary DVE/Xvfb processes exited normally.

## Automation regression

```bash
python3 verification/coverage/test_dve_coverage.py -v
```

These license-free tests mock the DVE APIs to exercise guards and CSV
serialization; they do not establish native DVE merge correctness. Also
test native DVE with compatible instrumented builds and real test VDBs.

The hardened wrapper was tested with native DVE: the two-test `merge_smoke`
CSV remained byte-for-byte identical to the earlier successful merge.
An incompatible test VDB that DVE skipped with `CMR-VCINF` now fails the
wrapper and retains only the partial CSV plus diagnostics, not `summary.csv`.
The historical Ara VADD export also remained byte-for-byte unchanged. A VDB
containing both a valid test and an empty interrupted-test directory was
rejected by native DVE's Tcl exporter, with the incomplete path recorded.
All 12 license-free regression tests passed, including concurrent output
claims, the row limit, timeout failure, CSV quoting and CRLF input lists.
