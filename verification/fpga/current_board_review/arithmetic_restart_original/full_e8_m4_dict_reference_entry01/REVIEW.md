# E8/M4 Full4095 Reference Entry

**NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT**.
The parent-authorized single reference may proceed under Zeno's bounded
executor. No additional source-review approval round is required. This is not
a reference PASS, DUT admission or Linux stall closure.

Source: `../full_e8_m4_dict_prepare01/`.
All126 pinned files were independently hashed with zero mismatches (actual
checking exit0). No compiler, Host, Spike, DUT or raw-trace parse was run here.
Exact pins and ELF identities are in review.json.

## Source And Oracle

Original identity is recovery22's byte-equivalent Linux ELF/disassembly,
not recovered original C bytes. The adapter retains all4095 seed/op/VL/mask/start
calls, three seeds,25 operations, returned vstart and13-instruction helpers,
without prefix truncation, partition resets or inserted vector operations.

The source diff limits changes to exact-cap qualification, aligned output,
packed scalar initialization/mask copies, and dictionary fast comparison.
Original fallback remains verbatim, including its original guard diagnostic:
a leading-guard failure reports the final guard value. That peculiarity is
preserved, not silently fixed. Actual original/packed mutation logs match.

Python-generated words are checked in the existing Host against original C
value/oracle logic for every one of2096640 result positions and both8190
guards. Reduction uses masked modular accumulation with nonzeroVL element0;
compress uses packed selected-source order; gather uses original capacity
bounds; signed/unsigned division handles zero and signed-min/-1. The unchanged
C RNG loop and all input bytes/predicate bytes are checked at every helper call.
This shape has no FP operations or invented fflags oracle.

Both actual Host variants exit0 for complete positives,1 for each of seven
semantic corruption classes, and-4 for the explicit shift64 sanitizer probe.
Original compile-warning/missing-UBSan-library failures remain preserved.
Host03 uses trap instrumentation, not disabled checking.

## Packing And Actual ELF

10172 dictionary words and uint16 indices with maximum10171 use614110 total
ROM bytes including masks. Every successful call checks64 complete8-byte words
and the final2 bytes, exactly514 bytes including guards. Every call initializes
that full footprint; per original ordering mask128 bytes are initialized per
mask configuration and reused across its start trials. Its upper64 bytes stay
zero. No output+1 uint64 cast or rounded-up520-byte access is introduced.

Byte-pointer memcpy is alias-safe even at the explicit Host unaligned address.
All pointer offsets stay inside the actual arrays. Actual lowering has scalar
ld/sd/lhu/sh for the fast path, not extra RVV. The leading guard is part of the
first word; result511 and trailing guard occupy the last halfword.

Independent read-only ELF program-segment extraction matched each of26 actual
helper/capacity windows in both ELFs to one unique original machine-byte
window (328 instructions:25*13 pluscapacity3). Actual loaded segments stay in
1MiB and out is8-byte aligned. Stack gaps are424808/416416 bytes for SoC/Spike,
both above the64KiB reserve. Runtime stack does not hold dictionary/index ROM.

## Reference Bound And Interpretation

Use these existing pinned ELFs; do not rebuild. Before the sole attempt record
the exact executable/profile/step/time/raw-size limits, then retain actual wait
exit and pre/post input hashes. A timeout or step/file limit is not a hardware
bug; preserve the run without retry, reducing scope or increasing its bound.

The3000000 firmware-instruction target is a cost admission criterion, not a
measured result. Any completed count above it remains HOLD for later DUT
review. Existing rates are proxies; original vector division/remainder can
change throughput. No current3h hardware guarantee follows from this review.

