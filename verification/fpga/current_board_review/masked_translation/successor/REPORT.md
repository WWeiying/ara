# AddrGen Before/After Report

2026-10-10. Completed comparison; no additional simulation for this report.

## Identity and Outcome

- `before01`: original RTL from `measurement04/frozen`; five controls complete
  successfully, then all-off case0 FAILS at its first MMU request to 0x40001000
  (oracle requires zero requests).
- `after03`: candidate **32/32 local PASS**, no RTL assertion errors.
- The two frozen TB files are byte-for-byte identical. SHA256:
  `56bd5046f8102fae32bc20120253554a58911e37a0d9387e0edd6b03bdb2de7a`.
- Source manifests differ ONLY in `hardware/src/vlsu/addrgen.sv`:
  before `a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988`;
  after `470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da`.

The frozen before01 runner applies a later fatal to its whole-log status filter,
so its status.json conservatively labels the entire batch FAIL. Its five earlier
LOCAL_PASS sections contain no errors and were compared independently below.
No original status, log or snapshot was rewritten. The current runner's corrected
per-section reporting was checked on existing logs only: five PASS, one FAIL.

## Five Unchanged Controls

All CONFIG/MMU/AXI/DESC/ACK/LOCAL_PASS events and their cycle numbers are identical,
not just final values. Counts and cycles below apply equally before and after.
Translation enable is distinct from the instruction's vm bit.

| Case | Control | Descriptors / AXI / MMU | Ack Cycle | Final Cycle |
| --- | --- | --- | --- | --- |
| 21 | Unmasked burst, translation enabled | 1 / 1 / 1 | 7 | 13 |
| 22 | Unmasked burst, translation disabled | 1 / 1 / 0 | 4 | 10 |
| 23 | Masked indexed sparse | 8 / 3 / 3 | 21 | 26 |
| 24 | Masked indexed all-off | 8 / 0 / 0 | 12 | 17 |
| 25 | Masked indexed vstart3 | 5 / 2 / 2 | 15 | 20 |

## Fixture Corrections Before Accepted Runs

1. `after01` had consumer-ready high while the descriptor FIFO was empty.
   AddrGen uses that input directly as pop (`addrgen.sv:153`), causing FIFO
   assertions. The fixture now gates it with descriptor_valid; the runner also
   rejects nonfatal RTL assertion errors. after01 is excluded from acceptance.
2. `after02` packed mask/index lane-local subelements linearly instead of using
   Ara's existing bit-reversed subelement layout. This explains case3/20's
   element21 request versus the fixed oracle's element22, and case23's wrong
   skip at element4. Only input packing changed. The independent permutation
   was checked against all128 existing e8/e16/e32/e64 byte-table entries.
   Predicate pattern, expected active elements/addresses, exception oracle and
   completion counts did not change. after03 also batches reset-isolated cases
   in one simulator process. All old failure records remain available.

## Masked All-On Cost and Limits

The candidate converts masked ordinary unit-stride to element transactions.
Measured case19 (e16/VL49, all active, modeled backpressure) emits **49 AR,
49 translations and 49 descriptors**, ack cycle245, final cycle254. This is a
real transaction-count cost, not performance-neutral burst preservation.
The two unmasked controls retain their old burst/cycle behavior but do not
quantify masked slowdown. No matched before/after all-on timing ratio was
measured; do not compare case19's cycles with the different VL8 controls.

Only AddrGen is real RTL here. MMU, mask windows, index source, descriptor sink
and parent lifetime are models; no real VLDU/VSTU, R/W/B data, Sv39 or original
ELF execution is claimed. These are directed reconstructed cases, not full
original-source replay. Parent's subsequent VLDU changes are outside these
frozen tests. No production RTL was edited and no random/new cases were added.
