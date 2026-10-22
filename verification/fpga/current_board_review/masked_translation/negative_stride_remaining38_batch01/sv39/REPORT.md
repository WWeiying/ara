# Remaining38 Sv39 Software Reference

Status: **38/38 reference PASS, 10 groups (9x4 + 1x2); NOT DUT acceptance**.
All 20 original prepared SoC/Spike ELFs remain unchanged in `software01/group00..09`.
Manifest and source proofs preserve exact original group/member order and each original
10-instruction load/store helper plus 3-instruction capacity helper. Runtime/ELF identity
is source-derived, not byte identity with archived Linux executables or Linux signal frames.
The original single source linkage does not prove equivalence to every lost parent failing trial.

| Group | Cases | Firmware records to HTIF | Checks | Spike seconds | Parser seconds | M6 estimated minutes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| group00 | 4 | 6,461,267 | 68,602 | 103.71 | 245.56 | 167.35 |
| group01 | 4 | 6,461,391 | 68,604 | 109.50 | 235.40 | 167.36 |
| group02 | 4 | 6,560,729 | 68,598 | 111.02 | 251.84 | 169.93 |
| group03 | 4 | 6,627,885 | 68,604 | 106.98 | 255.87 | 171.67 |
| group04 | 4 | 6,577,257 | 68,166 | 110.75 | 255.29 | 170.36 |
| group05 | 4 | 6,510,387 | 68,602 | 108.88 | 246.92 | 168.62 |
| group06 | 4 | 6,501,502 | 68,385 | 108.49 | 240.40 | 168.39 |
| group07 | 4 | 6,643,496 | 68,602 | 113.38 | 248.85 | 172.07 |
| group08 | 4 | 6,651,745 | 68,386 | 111.78 | 257.34 | 172.29 |
| group09 | 2 | 3,322,411 | 34,092 | 57.41 | 128.40 | 86.05 |

Totals: 62,318,070 firmware records, 650,641 actual scalar checks;
1041.88s summed actual Spike time and
2365.88s summed successful parser time.
These are child durations, not total wall-clock (hashing/Host/first failed parser excluded).
Firmware commit records may include a partial fault record and are not exact architectural minstret.
Every group separately proves five boot records, HTIF1, exact original park, restored CSR,
all four checkpoints, actual target addresses, same-PC nonzero restart, and full final data.
Actual Spike/parser waits are numeric zero in every `reference02/groupNN/complete.json`;
original group00 Spike receipt/raw is reused from `reference01`, not rerun.
The outer invocation receipt is `REFERENCE_OUTER_EXIT.json`. No systemd exit is inferred.

## Oracle Boundaries

14 fault cases restart at element2 or5; 24 all-off cases have no target memory fault,
retry or prefix poison. All preserve CAP64, VL8, original input/offset/mask setup,
two output guards, neighbor registers, full8KiB memory and PTE/physical guards.
u0 repairs data permissions without refill; u1 remaps/refills; all-off performs original
post-completion cleanup only. Completed prefix is checked and poisoned exactly once.
Unfinished active load suffix in the fault snapshot and permitted pending store suffix
are observed but not forced to an invented value. Final results and final memory are exact;
the retained **old fault snapshot** remains legitimately partially unconstrained.

## Preserved History

`reference01` remains NOT_ACCEPTED: the original parser rejected its static ownership set
before raw parsing because it omitted the real wrapper retry VSET (0082f2d7).
`checker02.py` adds only that instruction with exact owner/window/count checks; Host6
passed and the same group00 raw was parsed offline. Original Host fixture-negative
adjustments and CSV Host draft failure have separate receipts; no original record overwritten.
Original fixture/checker Host9 passed. Current software/reference SHA inventory is in
`READY.json`, SHA `07ed5a60755b197b907cfbaf2038692093e357b2e7c2149b51106944af14d2c4`.

## M6 Execution Boundary

Cost estimates use the measured accepted M6 store pilot throughput plus20%, not M7.
Highest estimate: 10337.13s;
all groups under10800s estimate: True.
No software optimization/rebuild has been performed. The sealed M6 image alone may be used
for the authorized two-lane background replay; M7 fixes/acceptance remain separate.
The draft grouped CSV checker is in `vcs_m6_plan01`; its launch integration is not yet
accepted. Reference READY does not authorize bypassing that terminal oracle or numeric exits.
No DUT has been started by this preparation. Do not reuse the earlier7200s rough estimate.
