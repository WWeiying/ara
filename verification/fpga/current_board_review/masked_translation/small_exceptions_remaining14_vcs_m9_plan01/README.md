# M9 Remaining Fourteen Replay

Minimal successor of the accepted M9 two-single replay. Exact software READY
`3e3b774785788916e41031ef652c63c8b6e0b9cc507dc9a0dc67e9746006824a`.
No ELF recompilation, DUT build, or reference replay. Original1253 software
pins, actual M9 image/source manifest, all imported verification modules and
new worker/checker/hook/Host outputs are bound into prepared01/plan.json.

Jobs8;1800s/case;6900s worker deadline;7200s service hard bound. Exact14 cases
use original VL8, eleven helper instructions, capacity3, complete130 outputs,
sixteen mask bytes, data/PTE/guards/CSR and four nonempty owner lifecycles.
Only source sc0 final output slots5..8 are undefined. Actual-ELF main/handler
opaque first-spill checking is inherited unchanged from the accepted preparation.

The original common runner persists actual numeric monitor/child outcomes
before postchecking. Generic protocol validation and one full source-checker
traversal are mandatory. Exact runtime labels are distinct from historical
source names. Real raw console/run.vcs.log failures veto a PASS marker;
partial FAIL stops the live monitor without waiting for final output.
No FSDB, coverage, retry, timeout increase, alternate image or softened oracle.

Root firstfailure.json is exclusive and thread-serialized. Checker type,
message, row/cycle/event/PC/insn where available, short traceback and stage
survive later sticky-abort failures. Numeric child0/17 is never relabeled by
a postcheck exception. Original producer records remain untouched.

New service is `ara-small-exceptions14-m9-01.service`, direct Python MainPID,
KillMode=control-group, Restart=no, ExecStopPost pinned_service_exit.py.
The hook records only actual systemd exit fields and time, not invented wait0.
Prepare/dryrun do not query live jobs. Actual authorized run performs one
fresh host inventory, cap24/MemAvailable32GiB, then launches. Resource refusal
is not retried. Eventual PASS is these14 source ports, not historical Linux
process/parent closure or proof of zero physical MMU requests.

Independent entry result schema required by authorization_gate:
decision NO_BLOCKER; blockers []; plan_sha256; worker_sha256; checker_sha256;
reference_ready_sha256. Those identities must match the final files.
