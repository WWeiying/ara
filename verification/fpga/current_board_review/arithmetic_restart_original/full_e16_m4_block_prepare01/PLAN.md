# Original e16/m4 Full4095 Software Reference

CAP256/vtype10 are tied to the archived ELF and original e16/m4 helpers.
The binary-equivalent reconstructed C retains three seeds, every helper call,
RNG/history/mask group reuse and the original failure fallback verbatim.
The only business adaptation uses legal byte memcpy scalar initialization and
eight exact 64-byte dictionary blocks plus the final 4-byte result/guard pair.
No output checksum, call partition, reduced result scope or extra RVV.

Original flat data exceed 1MiB; actual source-derived dictionary blocks and4095x9 uint16
indices fit. Host must compare the original C and packed path on every result,
guard and physical predicate byte, including typed005b, high bytes, UB trap,
unaligned byte memcpy and protected page tail4. Actual compiled helper bytes,
no-extra-RVV, LOAD map and64KiB stack gap are admission facts, not estimates.

One reference is allowed only after actual independent final entry. Its finite
debug script is rs4000000 then quit; wall120s/raw768MiB, full EOF oracle, and
firmware cost gate3M. Numeric wait is saved before postchecks. Any failure stays
NOT_ACCEPTED with no automatic retry. No DUT or production RTL/image changes.
