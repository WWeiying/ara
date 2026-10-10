# Dual-source low-mantissa operand coverage

This batch keeps the frozen old VCS image and extends the completed
673-PASS aggregate from gap77. No RTL repair or processor rebuild is made.

## Evidence and falsifiable coverage hypothesis

Gap77 did not improve vector operand LZC coverage. Its initial target count
of 381 was mixed-metric; filtering condition alone gives 321 unhit points.
The isolated diagnostic `verification/out/lzc-calibration-20261006-01`
compiles the actual common_cells LZC for WIDTH 10/23, MODE 1. It exhausts
all 1,024 FP16 mantissas and tests zero, all-one, one-hot and all two-hot
FP32 patterns. Its software bit-scan oracle passes. Diagnostic VDBs are
never appended to processor coverage.

The diagnostic LZC condition checksums and widths exactly match 36 MFPU
queue LZC instances in the old image. Of their 321 unhit condition points,
21 are hit by the isolated diagnostic; 300 are unhit in both. The latter
are not automatically waived: native truth-table review is still needed.

The 21 demonstrably reachable misses are in FP16 MFPU A/C LZC instances,
mostly raw position 1, with additional positions 7/8/21/28 in selected
lane-C instances. Gap77 leaves one multiplication source fixed at 1.0;
also a one-hot index derived directly from the global element index can
correlate with lane ownership. The new hypothesis is that feeding low
mantissa patterns to both sources, shared across groups of four adjacent
elements, reaches the remaining feasible A/C conditions. This hypothesis
is rejected if the completed PASS bitmap union shows no corresponding
new points; mere functional PASS does not establish coverage improvement.

## Four tests and acceptance

`vgap78_add16`, `vgap78_add32`, `vgap78_sub16`, `vgap78_sub32` use
`vfwadd.vv`/`vfwsub.vv`. Source A cycles zero/low bit 0/low bit 1/both;
source B cycles signed one-hot subnormals. Both sources vary instead of
one being fixed at 1. Inputs stay finite and widening addition/subtraction
is exact; fflags must remain zero. The scalar numerical oracle, Spike
full scalar/vector comparison, destination-tail/mask checks and clean DUT
contract are all mandatory. Cases use LMUL 1/2, seven VL/mask combinations.

The dispatcher statically selects `OpQueueConversionWideFP2` on both
sources for VFWADD and VFWSUB, ensuring this tests the intended conversion
path. No known unordered-reduction failure is re-executed or repaired.
Only compatible PASS VDBs extend the aggregate; failures remain excluded.

Output: `verification/out/gap78-old-image-20261006-01`.
Progress: `./vstatus jobs gap78` from the verification worktree.

## Measured acceptance and coverage additions

All four tests passed full scalar/vector comparison and DUT checks.
FP16 cases each have 1,820 self-checks; FP32 cases each have 924.
Their compatible PASS bitmap union adds 14 line points, 78 condition
points and 21 branch points, with no FSM addition. Raw point counts must
not be interpreted as percentage-point increases.

The condition-only source target audit proves 16 newly hit MFPU queue
LZC points, reducing its historical condition deficit from 321 to 305.
Evidence is `lzc-condition-delta.json`, not merely the fact that four
tests passed. The 16 targeted additions occur in FP16 lane A/C LZC
instances; much of the other aggregate gain is scalar FP comparison and
arbitration used by the independent numerical oracle.

The 677-PASS native DVE export completed: raw i_system line 80.40%,
condition 81.16%, branch 79.97%, FSM 60.46%, toggle 62.89%.
Status and coverage_status are COMPLETE. No failed reduction or isolated
diagnostic VDB is admitted.
