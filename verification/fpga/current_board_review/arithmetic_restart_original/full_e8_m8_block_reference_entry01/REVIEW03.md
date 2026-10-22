# Full-Unroll Reference Entry

Decision: NO_BLOCKER for Aquinas's sole bounded software reference, not DUT.
Exact entry SHA: bb5d14057c05f8f0d1e19894619d988f97f5a3e8844c8087ae21ff0efd68d777.
All 153 entry pins were freshly verified. No reference directory existed at review.

The initial cost estimate is superseded by static_cost02: the line parser had
swallowed the LD after a bare RET. Actual comparator success is 451 instructions
plus six caller instructions. Net saving is 446880, not 450975; predicted firmware
is 2825046, or 2835046 with the proposed 10000 reserve. This exceeds the required
271926 saving without claiming a measured new runtime. The actual original
sequence independently gives 4095 calls, 525 seed/op/VL groups and 1575 mask
groups: initializer -147420, comparator -298935, VL setup +1050, after-mask -1575.
See ACTUAL_UNROLL_REVIEW01.md for the independent instruction/CFG review.

Original source, model, RNG/order, dictionary and fallback are unchanged. Actual
26 helper routines match original bytes. No added RVV, aliasing cast or widened
tail access: fixed-size memcpy covers 128 words plus exactly two bytes. Comparator
has no stack traffic; main frame remains 304 bytes. Allocated growth is 1984 bytes;
actual .text growth is 1998 SoC / 1994 Spike bytes. Both stack gaps exceed 64KiB.

The new lifecycle binds the actual 129-store PC/code/width/offset schedule,
including SH after 100 SDs, then remaining 28 SDs. Every call requires fresh full
1026-byte initialization. BSS initialization remains a separate ordered phase;
the dictionary is read-only, selected by original ordinal, not mutable history.
The eight-register reference observer differs only in local path and trailing
newlines; all full-result, guard, CSR, helper and exit checks remain mandatory.

Existing Host receipts were read, not rerun. The 18 paired original/packed
processes retain full positive and corruption outcomes. Focused first receipt
really exits 1: 15 semantic tests pass, one text comparison mistakenly used
literal backslash+n in rstrip. A separate test fixes only that comparison,
requires equal ASTs and exits 0. No failed receipt is relabeled PASS.

Executor reviewed: exactly one fresh reference01, fixed 4M hard steps / 120s /
768MiB raw; durable numeric execution result before the one bounded 600s audit.
All pins are checked before/after. Complete firmware above 3M writes HOLD, not
READY. No automatic retry, no DUT, no old raw parse, no old HOLD modification.
