# Prepared Terminal Waiter

Only preparation is authorized. No waiter/service, simulator, reference, build,
live CSV read, or service query is started by preparation or Host tests.
Original plan, worker, inputs and outputs remain untouched.

After main authorization, from this directory:

```sh
python3 -B waiter.py wait --authorize-wait --ready-sha256 READY_SHA --out "$PWD/terminal01"
```

Main may place this command in a fresh independent service with a 6100-second
outer bound. It never controls or stops the original simulation service.
`READY_SHA` must be the actual sealed READY.json SHA. The output must not exist.
There is no retry or resume after a failed or interrupted full CSV pass.

The waiter registers inotify before checking for atomically published
`prepared01/complete.json`. Only directory events are observed while waiting
(maximum 5400 seconds); no active CSV, process, or service polling occurs.
Missing terminal publication is NOT_ACCEPTED, not a hardware diagnosis.
Whole PASS, runner COMPLETE, exact membership, durable child and actual monitor
numeric zero, no abort/timeout/failure, and exact command/ELF/image/pins are required
before CSV opening. Terminal failure never starts a CSV audit.

After admission, a single full CSV pass (offline bound 600 seconds) combines the
existing generic CVX/architecture/uop validator with independent scalar-read
synthesis and SHA-256. It checks actual code/addresses/BE/load extension,
17274 scalar equalities, all four 4096-halfword memory phases, 2048-halfword
refill, 64 results, two original and 64 extra storage guards, original ten-helper
sequence, capacity, actual fault13 at P-18/vstart5, completion ecall9, same-PC
retry with original P+22 base and stride -8, returned vstart and raw CTRL0.
Vector data evidence is subsequent scalar loads, not direct RVFI vector payload.

The original worker's full initial/final maps, page-table/neighbor/CSR oracle
remain bound by strict_prefix.json and complete.json evidence hashes. Its
source-oracle executor is NOT run again. The reference raw is not parsed again.
All original input pins and new transitive imports are checked before/after;
the terminal CSV is hashed inside its single parse, with file identity checked
before/after. Original service exit is explicitly NOT_QUERIED_NOT_PROVEN:
durable monitor0 and captured launch ownership are not invented systemd exit
evidence, and collected-unit defaults are never consulted.

Scope: one source-derived real Sv39 single only, not Linux signalframe semantics
or the original 96-case parent. A failure reports the first checker exception
without changing DUT state or re-reading the full CSV.
