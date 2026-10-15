# Runner Timeout Classification Review

Decision: **NO_BLOCKER** for the narrow current-source classification change.
Independent static review only; no tests, simulator, reference or build executed.

## Findings

- `verification/ara_verify/runner.py:195` checks cancellation before the
  deadline check. Cancellation observed there leaves `timed_out=False`, so
  `_run_test` still returns CANCELLED with the actual child return code.
  Pre-start cancellation paths are unchanged.
- `runner.py:212-214` alone sets `timed_out=True`. Prioritizing that captured
  result at line500 prevents a subsequent sticky batch abort from relabeling
  an established timeout. This does not infer timeout merely from cancellation
  or elapsed time in the post-processing path.
- Race boundary: cancellation arriving after the monitor's cancellation check
  can coincide with its deadline check. If the monitor records timeout, TIMEOUT
  now wins. This is the intended precedence, not proof of the wall-clock order
  of two concurrent events. Cancellation observed before that check remains
  CANCELLED.
- `_run_monitored` still returns `process.returncode` unchanged. TIMEOUT retains
  its existing public `TestResult.returncode=None` convention; CANCELLED retains
  the actual code. For the newly corrected both-flags case, the public result
  consequently changes from CANCELLED/raw code to TIMEOUT/None. No raw receipt
  is rewritten, and None must not be described as the actual child exit code.
- Probe and contract evidence collection still precedes classification.
  The inspected runner diff changes only the two branch positions and a
  comment, not process stopping, monitor logic, protocol checks or RTL.
  It does not update frozen M9 copies or historical artifacts. This review did
  not independently rehash the frozen image; its scope is the current patch.

## Test Evidence And Scope

The added tests exercise timeout with/without sticky abort and external
cancel without timeout, including preserved CANCELLED return code -15 and
contract evidence on timeout. Parent reports actual exit0, **58 passed in
23.73s** across runner, signals and contract tests. This includes the earlier
32 tests, not 90 tests. Results were not rerun by this reviewer.

Reviewed SHA256 identities:

| File | SHA256 |
| --- | --- |
| `verification/ara_verify/runner.py` | `51ddd4d7ef370ea287c3d2ccd75238008a7cd37916b5e1cbf8691ce5b088dfeb` |
| `verification/tests/test_runner_contract.py` | `11c7714bc610746d62010d624ca6a8aa5ec45eff1550db25763e7758661dae4e` |
| `RUNNER_TIMEOUT_CLASSIFICATION.md` | `59f1df14c23d11c18c5b88811655bc0dfa355bc10fd923aa14dba910758a7fed` |

No implementation changes requested. Only this review document was added.
