# Original Recovery Plan Not Admitted

Plan01 SHA3ce5268b58f38e3c565d44690fe759a95a88618f15d8f2ec28b3aa251d4bf537
was prepared but never executed. Hilbert found a late-abort window during large
strict report save/hash before publication. Preserve its plan, code and Host
receipts unchanged; this is an executor issue, not a new DUT failure.

runner02.py reuses its exact checker, provenance and pins. After all expensive
validation and strict report save/hash it checks the sticky abort again. Only
the final small result publication blocks SIGINT/SIGTERM, rejects pending signals
and commits the decision. Signals remain blocked until immediate process exit;
signals arriving after this terminal decision are not a new validation epoch.
Outer actual wait0 and not timed_out are still mandatory. Four new tiny Host
tests exercise cancellation during save/hash, actual pending SIGTERM and normal
publication. The original 12 checker tests are not rerun.

Final entry uses prepared02/plan.json, runner02.py and the same independent review
schema described in README. Fullparse01 is under prepared02, not the old plan.
The fixed600s child bound and no-retry/no-DUT constraints are unchanged.
