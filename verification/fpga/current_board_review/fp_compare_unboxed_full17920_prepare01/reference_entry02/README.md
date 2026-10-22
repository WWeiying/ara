# Reference Entry02: Host Receipt Identity Fix

Status: **prepared, independent successor entry review pending; reference not run**.
Original `reference_entry01` remains unchanged and NOT_ADMITTED because its
executor re-baselined the current Host receipt/log instead of checking the
already bound `ENTRY.host_wait_sha256`. This is an entry-gate defect, not a
source/model, reference or DUT failure. Aquinas's exact HOLD review is retained
under `fp_compare_unboxed_full17920_source_review01/REFERENCE_ENTRY01_REVIEW.*`.

This successor copies the exact checker, actual-ELF spec,22-test script and actual
Host receipt/log unchanged. Those22 tests are **reused, not rerun here**.
`execute_once.py` now verifies the Host wait SHA from ENTRY, then requires
`type(actual_wait_exit) is int`, exit0 and `timed_out is False`, and verifies the
log SHA recorded in that exact receipt BEFORE adding any current hash to the run
input ledger. Ordinary fresh-input checks still follow. No oracle is relaxed.

Six new short metadata tests passed, actual wait0 recorded in `gate.wait.json`:
valid receipt; replaced receipt still claiming numeric0; changed log; Boolean
False masquerading as exit0; numeric0 masquerading as timeoutFalse; actual exit1.
The old metadata cannot be silently replaced while preserving ENTRY and review.

All remaining scope and fixed limits are unchanged from entry01:
17920 calls/286720 bits/35840 guards/flags/vstart;185 static helper encodings,
326144 dynamic helper instructions pluscapacity3;41 stores/8inputLD/LWU percall,
2240 hoisted records; DK0 fixed old and original malformed raw scalar boxing.
Same compiled ELF, actual ISA, unique `rs4000000;quit`,120s/768MiB raw,
one600s closed audit,3M firmware gate, purepark EOF. No retry, build or automatic
VCS. Input drift or any actual child/audit error is retained as NOT_ACCEPTED.

## Exact Entry

- ENTRY SHA `63647edc1479e91ec27377e5fe206e9064d114b75dacd7b05c59e805b59ff3c6`
- input_pins SHA `aa51cee0488c76be74c8277241142bd6eb121fe657901a2667d756129c88a3e3`
- executor SHA `0ecda41e8b01914806a7ad4b2d9ad4ad689582cc010d2e44a6410e9191f332d8`
- checker remains `1533ae8fc44b0619bea67dde7427ef128630076155e5b1f9e1404084889e832e`

Actual independent review must bind the first two hashes with status
`NO_BLOCKER_REFERENCE_ENTRY`. Only then the parent's conditional authorization
permits the sole command printed in ENTRY, using that real review path/SHA.
Neither parent prose nor this README substitutes for that independent binding.
