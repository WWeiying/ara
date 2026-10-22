# One Mask-Clear Candidate, Static Entry

Only software01/case.c's original128-byte zero loop is replaced by
initialize_mask_zero(mask), with one header include after the existing mask
declaration. All other source bytes, FP refresh loops, selected32-position
bit construction, RNG, packed oracle, exact fallback and full5985 order remain.

mask_clear.h performs16 fixed8-byte builtin memcpy writes at offsets0..120.
Its interface is void*, and the accesses use unsigned-char byte offsets:
no uint64 pointer dereference, assumed alignment, alias cast, rounding up, or
byte beyond127. The existing mask allocation is128B. Upper124 bytes remain
zero after the original selected32-position bitset loop. Each of2205 groups
still completely initializes all128 bytes.

An empty volatile compiler memory fence follows each memcpy. It is not a
hardware fence, software delay, new vector instruction or change to the
helper. It prevents coalescing consecutive stores across compiler-visible
memory boundaries into a byte memset/library loop. No other compiler flag or
algorithm change is proposed. Actual code is decisive: require exactly16
scalar SD, offsets0..120, at the real group entry; no call, memset, byte-clear
loop or RVV in that initialization path. Failure is HOLD, not another variant.

After independent source NO_BLOCKER, one Host/compile preparation may run.
Reuse software01 original full5985 Host receipts, exact helper source and
tables unchanged. New candidate Host must match all12 old original full
positive/negative logs, retain both equal-old-value deleted-FP-write negatives,
and exercise dirty128B clear at unaligned addresses and protected-page edges.
Actual ELF must preserve all458 original helper instructions and extra RVV0;
map/stack >=64KiB, all17 output reads/writes, original per-FP-call64 SW and
mask group lifecycle must be re-inspected, with no universal PC delta.
Recalculate the actual CFG net upper; reference remains unauthorized even if
<=3M. No new reference, DUT, RTL, or old-directory modification.

Old compiled positive mandatorycore3151890 / upper3320678 was HOLD. Proposed
store-only saving(384-16)*2205=811440 is not a measured or compiled result.
Register setup/spills/control changes must be included in the new actual CFG.
