# Original700 Independent Terminal Collector

Entry is `../prefix700_entry_review01/entry03.json` (12f51b0f...).
Zeno alone launched prepared03; this directory never launches DUT/reference/build.
The collector is authorized by main's existing conditional-terminal instruction.

`READY.json` binds producer PID/start ticks/boot/cgroup, actual launch receipts,
plan f1472802..., ENTRY, source/image/imports and seven passing Host tests.
It opens a pidfd once and does not read active CSV. Wait is bounded to 9000s;
the single closed-CSV audit subprocess is bounded to 1500s, collector to 10800s.
These bounds do not change the DUT's 7200s/9000s case/service budgets.

Success requires whole producer PASS, persisted numeric monitor0/no abort,
actual retained-systemd exit0 (not GC defaults), immutable inputs and one full
lossless CSV audit. The audit preserves all 700 calls/699 predecessors,
358400 result bits/1400 guards/700 fflags/vstarts/12880 helper instructions,
six-event lifecycle, 2800 required helper memory owners and 596 nonempty target
owners. Expected owner count is independently derived, not setup-only.

On a closed producer failure the same one-pass checker stops at its first
semantic/protocol error and records source tuple/PC/cycle when available.
Remaining bytes are hashed only, not reparsed. This branch cannot report PASS;
original producer failure and numeric exit remain untouched. Missing closure,
service provenance or pins fail closed. The audit subprocess's actual wait
result is persisted before postchecks. No retries or second semantic parse.

This is original first700 coverage, not full17920/Linux or direct vector-port
payload proof. `run01/attached.json` proves attachment only. Acceptance requires
`run01/TERMINAL.json`, `result.json` and `actual_exit_unvalidated.json` after exit.
