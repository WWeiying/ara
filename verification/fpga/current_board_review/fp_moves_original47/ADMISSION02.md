# Original47 Candidate03 Admission02

Status: **LAUNCHED, NOT TERMINAL ACCEPTANCE**. Parent authorized one fresh
admission after Tesla16 controls reached terminalPASS and released their two
reserved slots. No capacity increase, external termination, or automatic retry.

The refused `vcs_candidate03_01/` attempt, its pins and `candidate03.py` remain
unchanged. The thin `admit02.py` reuses its exact worker and mandatory terminal
postacceptance logic, changing only the fresh output and reservation accounting.

- Service: `ara-fp-moves-original47-candidate03.service`.
- Output: `vcs_candidate03_02/`.
- Unchanged47 reviewed ELF inputs, jobs2, timeout180 seconds/case, outer5400.
- One gate:11 live simv; NF7 two and alias one already counted live; Tesla
  reservation0; adding this request gives13/24. MemAvailable173.525GiB.
- Candidate03 image and original/prepared/frozen-source pins rechecked before
  admission; no rebuild or production/source/oracle edit.
- Actual candidate03 simv confirmed once: PIDs4113923 and4113924, running the
  archived e16/m1 op5 and op4 inputs from the fresh output. No further polling.

Evidence: [resource gate](vcs_candidate03_02/resource_gate.json),
[plan/pins](vcs_candidate03_02/plan.json),
[service launch](vcs_candidate03_02/launch.json),
[actual simv argv/cwd](vcs_candidate03_02/actual_simv_confirmation.json).

After terminal completion, `complete.json` can say
`PASS_47_ORIGINAL_SINGLES_CANDIDATE03` only after the runner is COMPLETE with
exact47 names/PASS/exit0, all original exact counts/markers and firmware exit
are checked, failure-marker veto passes, private inputs match, and image/source
pins remain unchanged. Until then this document is startup evidence only.
