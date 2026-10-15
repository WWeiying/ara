# Full E64 M1 Reference Pass, DUT Budget Hold

READY SHA256: 26ddbd6fc73864793c7472f1f8f34834eaf88d4b675468c2bd378713a6304e60

Only this next original cap16 shape was prepared. No RTL/image build, DUT,
larger-shape preparation, or edit of previously accepted inputs/artifacts.

The original C text remains unavailable; the accepted recovery22 reconstruction
rebuilds the original Linux ELF byte-identically. This preparation reverified
archive/recovery hashes, copied its runtime-only adaptation and retained the
entire original order: 35 operations,3 seeds,5985 calls,95760 results,11970
guards,5985 vstart checks,77805 helper instructions and128 mask bytes. All35
13-instruction helper windows and the capacity helper match the archived ELF.
No shortened operation loop, partition or fabricated fflags oracle was added.

- Original Linux ELF: 5c15d5227aacb7ccd7115f7f2379081f21d33c928358055caebe4dd480ceebe2
- SoC ELF: 57b2c91242d5b47edb776d8e83f24657e980b17c1bc80202bfc2317ffc0b9d9a
- Spike ELF: d0801428a6ebbfa2cd957e53add0379613708027971a3eea0aaab7c458263b49

New model uses64-bit FP inputs/operations and matches all640 archived FP table
entries before compilation. Original C full Host positive passed all5985 calls;
9 injected oracle negatives rejected. BSS Host1positive/11negatives passed.
One bounded Spike invocation exited0 in10.899971864s with397497233 raw bytes.
One full raw audit completed FULL_ORIGINAL_REFERENCE_PASS_NOT_DUT; actual audit
process exit0 is persisted, no retry. Firmware through HTIF:5908244 instructions.
READY contains complete source/code/reference pins and actual exit receipts.

## Fixed Three-Hour Assessment

| Measured M6 baseline | Actual firmware/s | New nominal seconds | With20% margin |
| --- | ---: | ---: | ---: |
| e32mf2:5922683 instructions/10026.130593s | 590.724701 | 10001.687735 | 12002.025282 |
| e16mf4:3806624 instructions/6406.345965s | 594.195821 | 9943.260776 | 11931.912932 |

Budget gate: BLOCKED_OVER_3H. Nominal projection is under10800s, but the same
conservative20% margin used for the preceding shape exceeds it by1202.03s.
These are instruction-rate extrapolations, not measured M7/e64 runtime; e64
division/sqrt latency and current contention could differ. No guaranteed
completion or proven impossibility is claimed. Under the requested conservative
admission rule, no M7 DUT was launched and no timeout was increased. Existing
ELFs/reference are available if main later explicitly accepts a hard10800s
bounded attempt with timeout risk; no such risk override is inferred here.
