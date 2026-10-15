# Independent Terminal Acceptance

`check_terminal.py` is a standalone read-only checker. It does not import or
modify the pinned live runner, execute programs, schedule jobs, poll, or write
reports into the campaign. Its JSON report goes to stdout. **It has not been
run against the current alias simulation output.** Use only after terminal
completion; startup or partial tuple PASS is not acceptance.

After the service has finished:

```sh
python3 -B verification/fpga/current_board_review/mask_alias_original/check_terminal.py \
  verification/fpga/current_board_review/mask_alias_original/vcs_candidate02_01
```

Exit0 means all six bounded partitions are accepted, not full-matrix or original
Linux acceptance. Exit1 means rejected evidence; exit2 means incomplete evidence.
Do not retry in a polling loop. A rejected checker result does not overwrite the
original runner result or establish an RTL defect by itself.

## Required Evidence

- Top-level terminal six-partition success, consistent launch/plan identity,
  and both tuple/prefix `run.json` files COMPLETE with completion timestamps.
- Exactly the expected three tuple names and three prefix names, no duplicates
  or extras, all statuses PASS and runner returncodes0. Terminal stage results
  must equal their separate summaries; tuple-before-prefix gate must be enabled.
- Every console has exactly the expected original `RVV_MASK_PASS` line with
  SEW and configuration count: tuple1, prefix98/66/98, errors0. Exact case
  begin/pass, replay-pass and historical VL512/vstart256 markers are required.
- Successful firmware exit must be `Core Test *** SUCCESS *** (tohost = 0)`.
  A success substring alone is insufficient.
- Failure markers take priority even when all success markers are also present:
  `RVV_MASK_FAIL`, capacity failure, `BOARD_CASE_FAIL`, replay failure/trap/
  mismatch, Core Test FAILED, fatal/assertion-failure patterns and standalone
  FAIL/FAILED/FATAL lines. Nonzero UVM_FATAL is rejected; its zero-count summary
  is not treated as a fatal event.
- Fixed reviewed programs/image manifest hashes anchor identity. Plan pins,
  prepared files, source ELFs, actual private `input.elf`, `inputs.json`, actual
  command preload/testcase/cwd, executable/generated image libraries and snapshot
  ledger are checked for consistency and current byte identity. CLI exposes no
  override for the reviewed manifest hashes.

This is a strict check of retained terminal artifacts and firmware acceptance,
not a new instruction-by-instruction reference comparison. It does not reread
or reinterpret a live commit trace or silently upgrade partial runs.

## Host Validation

Command executed:

```sh
python3 -B verification/fpga/current_board_review/mask_alias_original/test_check_terminal.py
```

Result: **9/9 tests PASS**, 0.154 seconds, exit0. All data were synthetic files
under an isolated temporary directory; no current simulation output was opened.
Coverage includes a valid acceptance with before/after file hashes unchanged,
eight contradictory success-plus-failure marker variants, absent terminal
report, RUNNING metadata despite success text, wrong count, private ELF drift,
nonzero firmware exit, nonzero runner returncode, and duplicate extra result.
The synthetic tests inject separate trust anchors through the Python API only;
the user CLI retains the exact candidate02 and bounded01 identities.

## Deferred Shared Runner Fix

After the current pinned tasks have completed, fix shared
`integration/run.py:oracle_complete` and the relevant shared runner failure
classification in a separately reviewed change. They currently require success
markers but do not explicitly veto all application-specific failure markers.
The fixed firmware's error-return path prevents ordinary failures from printing
PASS, but contradictory logs are not independently rejected by the old helper.

The future change should add failure-before-success precedence, exact case/
count matching where supplied by the program manifest, and host regressions
for contradictory/incomplete output. Preserve legitimate zero-count diagnostic
summaries and existing suites' marker contracts. Do not modify live pinned
helpers, relabel retained results, or change ELF/oracle expectations to make
this running campaign pass. The standalone checker supplies that additional
terminal acceptance layer without changing current execution.
