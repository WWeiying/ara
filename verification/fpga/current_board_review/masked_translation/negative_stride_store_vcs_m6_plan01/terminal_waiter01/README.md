# Conditional STORE Terminal Audit

Preparation only. No waiter service starts here. Aquinas entry review and
main authorization are required before executing the command in READY.json.
No DUT control, reference rerun or active CSV reads. Original worker inputs
remain unchanged.

The waiter uses inotify on producer complete.json, not simulation polling.
It refuses to read CSV unless the exact one-case producer is clean terminal
PASS, run.json COMPLETE, and both persisted child and monitored numeric
outcomes are integer zero, with no cancellation, failure or timeout and
elapsed <=5400s. Pins, image, private ELF, command, console and original
strict-result hashes are checked before and after the offline pass.

Exactly one closed CSV stream feeds both the existing six-event protocol
validator and independent scalar-read arithmetic. The full STORE numerical
contract has17275 equality calls, four complete4096-halfword memory scans,
64 original outputs/two guards/64 extra sentinels, all2048 refill writes,
capacity3, original10-instruction helper, actual fault15/tval40000fee/start5,
and same-PC retry with unchanged base40001016/stride-8. The target store's
two architecture owners and backend completions must precede handler entry;
marked scalar LHU observes127 before snapshot/repair, then prefix remains
poison36 and retry location becomes166. No LOAD-value oracle is inherited.

The worker's complete source/initialization/checkpoint oracle is bound by
its original strict-result and unchanged CSV hash; the terminal checker
does not rerun that source-oracle executor or reparse the Spike reference.
Its independent numerical and protocol pass cross-checks event coordinates.
CSV SHA is computed in that same pass, with inode/size/mtime stability checks.
No direct AXI AW/W/B signal proof, Linux signal-frame or parent96 claim.

Separate bounds: event wait7800s, offline audit600s, supervised child8420s,
direct owning service8500s. This does not alter any producer budget. The
service's MainPID must be the supervisor; actual subprocess wait return code
is fsynced into wait_receipt.json before final acceptance. A failed or timed
out audit is not retried. No missing-PID or garbage-collected systemd default
is used to infer historical process success. Offline result.json alone is
not final acceptance: require supervisor complete.json and actual wait0.

Host tests use the sealed STORE fixture only, not active DUT artifacts.
They cover terminal numeric/abort gates, full synthetic numerical scope,
six store/result/guard/completion corruptions, shared single-stream parsing,
atomic terminal publication, actual offline child exit0/nonzero and timeout.
Actual service properties are checked only when main launches the waiter.

Seal after Host passes:

```sh
python3 -B waiter.py seal
```

The launch array in READY.json requires replacement of ACTUAL_READY_SHA256
with the actual sealed READY hash. Do not launch until independent review
and main approval. The service targets fresh terminal01 and never overwrites
an earlier attempt.
