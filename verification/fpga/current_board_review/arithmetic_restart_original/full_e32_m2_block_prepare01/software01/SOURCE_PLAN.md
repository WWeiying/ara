# e32/m2 Full5985 Software Integration

Software-only successor of the accepted scalar candidate635f20f1. Original candidate and prior HOLDs are unchanged. No Spike/VCS entry point or authorization in this stage.

## Scope

Original reconstructed-C binary identity and the original e32/m2 assembly/operations header are retained. This is a source-port, not a Linux replay or original-C byte-identity claim. CAP64/SEW32/physical2,35ops,3seeds,5985 calls in original order,383040 results,11970 uint32 guards,5985 returned-vstart checks. Original FP table is640 exact uint32 bit patterns; no fflags oracle is introduced.

`case.c` comes from the sealed candidate via the mature bare-metal runtime adapter. Only output initialization and the successful output comparison path are packed. The complete original error fallback remains byte-identical. Output backing remains1026 uint32 entries; active footprint is exactly264B,33 uint64 transfers via memcpy, not alias casts. Word0 contains front guard+element0; word32 at offset256 contains element63+rear guard. No tail SH/LHU exists in this profile.

`model.py` is the accepted e32/m1 integer/exact-FP model specialized to CAP64 with its own source pins, RNG64 iterations per seed and gather index32 valid. It regenerates all5985 rows. Five uint16 block IDs per row refer to1499 deduplicated64B values. The final block's56 padding bytes exist only in ROM. Runtime compares only the final8B. Dictionary+IDs155786B; no call deduplication. Original FP640 table remains linked for fallback.

## Freshness and Host

`scalar_setup.h` is a byte-identical copy of the reviewed candidate. Every FP call executes128 interleaved typed a[i],b[i] assignments, with compiler-only barriers after each; total241920. Mask groups each clear16 exact8B ranges, then selected cumulative byte updates in original index order: mode0=64,mode1=32,mode2=9. Totals35280 clears and77175 SB-equivalent updates.

Host hooks observe C-level completed assignments in instrumented copies, not production code. Original and packed variants both run the full original C fallback against independently generated gold. Positive plus11 oracle mutations are compared byte-for-byte, covering active/prestart/inactive/tail, both uint32 guards, returned-vstart, signed zero, NaN bits and highest result. UBSan is enabled. Unaligned264B buffers, every-byte mutation and a protected page boundary check reject rounding up the last block.

Additional variants delete equal-old-value a63 or b63 on FP call1367, reorder pairs0/1, omit the initially-zero high mask clear, omit selected bit63, or reorder selected bits0/1. Event order, counts and cumulative mask values must reject all six. Host event evidence is explicitly not machine SW/SD/SB proof.

## Actual Artifact Gates

After integrated-source review: one Host/compile invocation via `execute.py`, each child90s and outer600s, numeric outcomes persisted before any postcheck. Same RISC-V GCC and O2 flags as accepted e32/m1, no auto vectorization, builtin optimization disabled except explicit memcpy idioms. Two backend ELFs are compiled, not executed. Verify458 archived helper instructions, no extra RVV, actual alignment, linked ROM and >=64KiB stack gap. A separate actual-CFG review must prove128 ordered SW per FP call,16 ordered SD before every selected SB path, all33 output stores/reads, call recurrence, frame sizes and positive-path upper<=3M. Until then status remains cost pending/HOLD; no reference authorization is implied.

`source_manifest.json` records initial generation. `SOURCE_FREEZE.json` supersedes it for review and execution, binding the finalized header declaration and this plan without erasing initial generation evidence.
