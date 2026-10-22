# Reference Observer Boundary

Read-only review of producer execution/command/STOPPED/OBSERVER_CAUSE metadata
and the pinned Spike ELF disassembly. No raw trace was reparsed or reference
rerun here.

Actual child receipt: exit0,10.546864655s, no timeout/retry, validated:false.
Producer reports the original full4095 console and minstret2646654. These are
not full raw-oracle acceptance. STOPPED retains Output setup writes beyond
exact514; no READY should follow from those receipts alone.

Producer's first-rejected record is line356, PC80000046/0002b023, zero-valued
8-byte write at80097b18. The actual ELF shows this PC is the pre-main BSS
sd-zero loop. out is80097918, so the write starts atout+512 and remains inside
the original1026-byte output array. The per-call514-byte initialization
contract was incorrectly applied to startup clearing. Static and retained
first-error evidence agree on an observer lifecycle mismatch, not a DUT bug.

A narrow offline successor is appropriate. Exempt only the actual startup
store with its zero value,8-byte alignment, valid BSS extent and pre-main
phase; require ordered complete BSS clearing. Keep the existing memory model.
Do not silently discard arbitrary stores outside arithmetic_main. Business
output writes still require the exact514-byte bound and fresh coverage for
every call. All65 reads,13-helper windows,CSR,input,vector-result and console
checks remain unchanged. Local negative tests should reject nonzero/bad-PC/
late startup, wide business write,cross-end and missing-fresh cases before the
authorized single closed-raw offline audit. Preserve the original failure.

Actual command binds source review ad414d879181c2a85d74acdb1db4c6d99523e80e545f4a0b12f9f9e7875378dc
and executor b19fba8bc50f2c474b0d4d0f469e9170597355d0b8972c2d40edd34fd04e5387.
This differs from reference_entry.json's proposed executor06c497c8 identity.
The actual code adapts to the earlier source-review schema and persists
additional preflight pins; it must not be described as byte-identical to the
later entry. Bounds/profile/ELFs stay the same. No second Spike run is needed.
