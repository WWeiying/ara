# Full482 Worker Entry Review

**HOLD: one P1 blocker. Do not launch plan `2e4be5e555d14eac74877535733783ad0970eefdd376328678d3e5a837236897`.**

At replay.py:314-315, the final abort read and direct complete.json write are separate. SIGTERM/SIGINT can invoke the active handler during json.dump/fsync and set abort after the last check; the file can still say PASS and line317 can return0. An already-started timer callback has the same window because Timer.cancel does not wait for it. Direct writing also exposes an unfinished terminal file.

Minimal correction: preserve this sealed plan/Host/code; use a narrow successor terminal publisher with a short synchronized deadline/terminal decision, signal pending/abort handling, and atomic final-file publication. Keep expensive evidence hashes/checkers outside the decision lock. Add bounded real-filesystem publication-time abort/deadline coverage; no need to repeat work05, Spike, or full synthetic482 matrix.

## Other Entry Checks
- Exact plan above, all832 current pins verified with zero mismatch. Checker SHA `ad52594870b9cbae5e20eb29e11f7e8feb5e8b952d507af24941546b872d0cc6`; runner SHA `806ffd79323272be404fbbb58b2b438d89ef16ced78ddf71c8efd77a859da47b`.
- Host02 SHA `ceaea5a3e4ff41d5bafc7f2d607fc515d695b68dfc30027dc696da1bccc6ba4f`, actual21 tests/exit0/51.510347403s; dryrun exact plan. Existing21 tests do not exercise final terminal publication, despite the handoff's late-abort statement.
- Owner ledger correctly requires2410 CAP memory owners and182 active targets (45 actual all-off), each with own completed alloc/done. No fixed2592-uop limit; extra reshape cannot replace a missing necessary owner. Corrected all-off test uses not any(maskbytes), not mode1. CSR transport replay is restricted to the frozen permitted rule and contributes no necessary data owner.
- All unused op1..7 PCs, including scalar load/ret, now rejected. Original helper continuity and full482 bounds remain.
- Reset profile binds the actual M8 image/snapshot/configuration, exact ELF/runtime and ten identical M6-to-M8 RTL files. Initial zero values are implementation evidence, not ISA defaults; unknown source/base remains rejected.
- Full65 actual scalar loads cover512 result bytes and two guards; final load low16 bits checked, upper48 deliberately permitted. Host corrupt result/guard/address/BE/source and missing freshness cases retained.
- Numeric monitor tuple is persisted before downstream checks; private command, direct worker MainPID/cgroup, cap24/MemAvailable gate, jobs1 and10800/12000/13200 budgets remain. Proxy5551.74s is not M8 measurement.
- No software conversion re-review, new Host execution, raw parse, Spike, DUT or live query in this entry review. Producer files unchanged.

Machine-readable report: REVIEW.json. Confucius notified immediately; a successor needs only the changed publication path/tests and fresh plan binding reviewed.
