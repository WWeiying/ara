# Unboxed265 Provenance Recovery and Successor

Original run remains **NOT_PASS / ERROR / INTERRUPTED**, with persisted child
returncode null and elapsed0 placeholder. No sealed plan, helper, source,
ELF, raw log, CSV, or terminal metadata has been changed. No new guest run.

## Root Cause

The sole command difference is argv[5], not seed (both1):

- Actual runtime: `+TESTCASE=fp_compare_unboxed_e16_mf4_prefix265`.
- Old expected: `+TESTCASE=rvv_fp_compare_unboxed_unmasked_e16_mf4`.

Original `replay.py:27` stores historical provenance in `case.original_name`.
The reused merge runner constructs the TestCase with runtime NAME at line262.
`gather_repair05/regression.py:211` instead expects `case.original_name` as the
runtime label. The shared contract was reused with the wrong metadata meaning.
`runtime_case()` supplies a COPY with original_name=case.id solely to the old
runtime artifact checker. The original case/historical provenance is retained.
No command field, input path, seed, or oracle check is ignored.

## Exit Evidence Limits

Sealed `check_artifacts:198` requires numeric rc0 and bounded elapsed before
the line212 command mismatch. The wrapper only calls that check after parent
PASS. Frozen `ara_verify/runner.py:513` also writes VALID trace_summary only
after numeric rc0. These imply rc0 through the recorded execution path;
they are NOT a persisted numeric process wait record. The exception escapes
postchecking and `runner.py:630` replaces the result with ERROR/null/0.0.
Consequently direct historical child rc and exact monotonic elapsed remain
unknown. Console CPU1225.070seconds is not wall time. No service-state query
or garbage-collected unit defaults are used to invent a process exit.

## Independent Architectural Result

The authoritative independent recovery is
`../../fp_compare_unboxed_prefix265_terminal_audit01/recovery01/result.json`,
SHA256 `0d468b20b1117c596023594be63c5abe7174e29045a14a53bbbea2b47850b479`.
Its reported status is `ARCHITECTURAL_RESULT_ACCEPTED_PROCESS_METADATA_ERROR`:
architecture accepted, process metadata NOT accepted; original batch preserved.
This is the independent producer's result, not an identity supplied by this
adapter. Scope is original265 prefix, not full parent17920 or Linux execution.

Our `offline.py` was started under the preceding offline-recheck authorization
before the instruction assigning unique CSV ownership to Aquinas arrived.
It had already finished (41.91seconds) when termination was attempted; no
process remained. `audit01/finding.json` is preserved as a duplicate parallel
audit, not a replacement for the independent result. It explicitly labels
inferred rc0 and a wall-window proxy, with direct persisted rc still null.
No subsequent full CSV read or re-execution was performed. Do not rerun it.

## Executable Successor (Not Launched)

`replay_successor.py` binds BOTH fixes into the actual reused worker:

1. The actual artifact callback adapts only the runtime-case copy.
2. Immediately after parent `_run_test` returns, before any postcheck, the
   wrapper writes and fsyncs `child_outcome.unvalidated.json` containing the
   returned name/status/numeric rc/elapsed/reason and command JSON/hash.

The outcome is explicitly unvalidated process evidence, NEVER architectural
acceptance. Checker exceptions retain that file and still set sticky abort.
No such record is retroactively created for the old run. Late-input validation,
explicit new parent authorization, frozen M6 image/config, original reference,
service ownership, resources, case5400/service6600/jobs1, no build/FSDB/retry
remain inherited. Unit is NEW `ara-fp-unboxed-original265-m6-02.service`.
The old approval cannot authorize its new unit or plan. Runtime resource
queries occur only on separately authorized run, not prepare/dryrun.

From this directory, the preparation commands are:

```sh
python3 -B replay_successor.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared_successor01" --authorize-prepare --reserved-slots 0
python3 -B replay_successor.py dryrun --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared_successor01" --plan-sha256 PLAN_SHA_FROM_READY
```

These commands are preparation only, not permission to rerun an accepted
architectural test. Actual future runtime command retains seed1, private
input.elf, testcase=case.id, NO_FSDB and its own commit_trace.csv. Dryrun uses
the source ELF by the inherited documented dryrun contract, not a private
simulation copy. Fresh plans/outputs are mandatory; no old directory reuse.

## Host Coverage

`host01.json`: 5 tests, zero failures/errors. Runtime-name copy passes while
old historical-name expectation fails; wrong testcase/seed/cwd/preload and
historical source identity are rejected. Forced postcheck exception preserves
rc0/elapsed/command identity; nonzero rc17 remains17 and stops further checking.
These are synthetic metadata tests, not new DUT acceptance. Their tested
functions are the ones bound by the executable successor; no new framework
or unrelated test matrix was introduced.
