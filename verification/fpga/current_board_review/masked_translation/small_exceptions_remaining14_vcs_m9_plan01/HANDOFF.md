# Final Worker Entry Review

Host34 PASS, actual exit0; dryrun14 PASS, actual exit0; no DUT started.
Plan: `prepared01/plan.json`, SHA256
`165c12dfee46c7949de188aedf779f914e8ee76260290017b2636e3fa168108f`.
Pins1271, preserving all1253 source/reference pins. Exact jobs8,
1800s/case,6900s worker,7200s systemd service. Parent launch authorization
is current; pending only the final worker short review and fresh actual
resource/direct-service gates. Reference review01 already says NO_BLOCKER.

| Entry | SHA256 |
| --- | --- |
| replay.py | f0346ed8de1b471b3cdb75829a674802ed102d66d9d77929f98851a9c69ef71b |
| checker.py | f72c1069cd219e4062668a5e6b554a95ff948a97cc9a3a2a2522b946d477aa34 |
| pinned_service_exit.py | 05ed8d7d400d9940d30f77bdbd287f40d9a5623e43bdf8c05bf3b4ed0718a517 |
| host01/status.json | 2e7e8c46a00b69c959777c74320cd86778665998c61280c3ead499a49832b678 |
| Reference READY | 3e3b774785788916e41031ef652c63c8b6e0b9cc507dc9a0dc67e9746006824a |

`checker.strict_csv` uses the accepted **abi_check.Checker**, passes every
CSV row unchanged and calls its full finish method. This is the identical
ABI -> source_owners -> full scalar oracle chain used by abi_check.analyze;
the local wrapper additionally catches construction/terminal errors and
persists phase/row/PC/encoding/traceback. It is not bare source_owners.analyze
or a relaxed checker. Generic validation remains independently mandatory.

Numeric outcomes are persisted before postcheck. Firstfailure is exclusive
and lock-protected, with original case/detail retained through late abort;
Host proves child0/17 and KeyError8 context are not erased. Partial raw FAIL
monitor ran a tiny Host process, not DUT. Service hook remains ExecStopPost,
not an internal fabricated wait receipt. Hook source has the same SHA as the
accepted two-case hook.

Tesla entry result required fields: decision="NO_BLOCKER", blockers=[],
plan_sha256, worker_sha256, checker_sha256, reference_ready_sha256, matching
the table. The actual result file's hash is supplied at run invocation and
rechecked at terminal. No source-reference rerun is requested for review.

Launch template is in prepared01/ready.json. Direct unit:
`ara-small-exceptions14-m9-01.service`; output prepared01/replay.
One fresh host inventory at authorized run requires external simv+8<=24
and MemAvailable>=32GiB. No external process is changed or killed.
After launch, only one actual private-ELF/cgroup/CSV-growth confirmation;
no long-job polling. Root terminal PASS cannot replace actual systemd hook
exit evidence; both must be checked after completion.
