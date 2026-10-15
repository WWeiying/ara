# Exact INTERRUPTED / ERROR1 Recovery Admission

**APPROVED_FOR_ONE_OFFLINE_PARSE_USING_RECOVER02. No remaining static blocker.**
Old review/decision/recover.py and the first failed admission remain unchanged.
The first static review missed the COMPLETE mismatch; this successor decision
uses actual run.json and the frozen worker's publication semantics, not a relabel.
No actual CSV/log, Host, reference or simulation was read/run by this reviewer.

## Actual Metadata and Causal Path

- replay/run.json is **INTERRUPTED**, status_counts **ERROR1**, correct sole runtime
  testcase, jobs1/seed1/default/5400s/commit_traceTrue/code_coverageFalse and
  completed_at. SHA29cd9c926d5a776628f07e63be0753617793cee6a0de5c47141acad223468686.
- Frozen parent _run_test originally returned PASS/int0. The owned wrapper
  persisted that classification, then the strict checker threw. Its except
  block sets the shared abort event and preserves POSTCHECK_EXCEPTION with
  actual monitor0/runner0 and exact whitelist error string.
- Frozen Runner.run catches that future exception into ERROR/returncodeNone/
  elapsed0.0; summary.json and complete.results contain that same result.
  `_write_reports` chooses INTERRUPTED whenever cancel_event is set, despite
  completed_at. Therefore COMPLETE is wrong for this real postcheck-failure path.
- Whole terminal stays NOT_PASS/abortedTrue/pins_unchangedFalse. Those flags are
  not converted into success. ERROR/None is not a failed simulator exit17:
  earlier durable monitor reports actual int0/1639.143087s/no-timeout/no-failure,
  with exact private runtime command; separate unvalidated runner record says
  PASS/int0 before the strict exception. No service/worker exit0 is inferred.

Only this exact combination can justify offline architectural-data recovery.
Accepting arbitrary INTERRUPTED, or changing it to COMPLETE, would be incorrect.
The corrected parser/protocol/full oracle must still pass before data acceptance.

## Exact Successor Diff and History

recover02.py SHA:
**c3e84a7c26f50625582cd9aee582c226e844f9b2b1585e8251488f6ee82d67b4**.
Only changes from original driver90bc2c22...:

1. Require exact `metadata.status == INTERRUPTED` and
   `metadata.status_counts == {'ERROR':1}`, preserving all existing scope gates.
2. Pin actual recover02.py and admission_attempt01.json in the new recovery
   input set. Remaining simulator/oracle/protocol/identity/output logic is identical.

admission_attempt01.json SHA:
**19c74aef51bd967632c4dff4710cd2309ad114c4e22268b7435cbc441bb17e47**.
It records Main's actual exec session76110/exit1,900s bound, metadata-admission
error, csv_reads0, offline01_createdFalse and no DUT rerun. Static control flow
confirms failed admission precedes out.mkdir and every CSV open. offline01 is
absent in the checked filesystem. This is a second **admission attempt**, not a
second CSV traversal or automatic retry of a failed numerical parse.

Original recover.py still hashes90bc2c22e46d055aa935d8038cdf4fa6623db9ec23bcb3a75b6e4cec53a61a1a.
checker598693ed... and hostf81ffb08... remain unchanged from review01. All66 calls,
65 predecessors,2178setup/2690bytes,33792results/132guards/33924LBU reads,
66vstarts/858helpers and strict six-event Observer protocol are unchanged.

## Decision Boundary

Main may execute recover02 exactly once, under the existing bounded offline
authorization, preserving actual child wait exit/logs and first failure. A
successful parse writes only new offline01 architectural recovery output;
the original NOT_PASS/ERROR/INTERRUPTED and original collector rejection stay.
No preclaimed architectural PASS, DUT rerun, reference rebuild, RTL edit,
unknown stall closure, full2688/Linux execution or parent acceptance.

This is a new static review; it does not replace prior review files or any
sealed producer inputs. No CSV, even the first14 lines, was inspected here.
