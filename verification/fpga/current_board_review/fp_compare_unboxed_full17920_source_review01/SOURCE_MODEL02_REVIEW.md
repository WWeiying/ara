# Source Model02 Short Review

Decision: **NO_BLOCKER_SOURCE_MODEL_ONLY** for the exact source hashes in the
adjacent JSON. No compile/reference/DUT approval is implied; the next compiler
stage still requires the parent's authorization. Producer model execution is
reported as Python0/7.874s, not C Host, linked-code or reference evidence. This
review read source and small metadata/hash evidence without running that model.
The prior source_model01 failure remains intact.

`software/case.c` preserves all nested loops,17920 calls, original eight helper
arguments and the complete DETAIL/final error behavior. Capacity is explicitly
constrained to16. The changed syscall/entry is the existing source-port adapter,
not a claim that the original Linux ELF ran. Source-specific geometry/flags and
the original 185 helper encodings remain as in REVIEW.md.

The table builder derives Z/O from each literal original allowed set, packs
baseflags/VL/Arow/Brow in disjoint record fields, and validates both possible bit
values independently against integer FP16 classification. 48 four-word periods
and2240 records preserve all32 seeds and original tuple order without deduplicating
calls. Header serialization uses fixed uint64 constants; no host-float golden.
Existing model_checks reports573440 bit-membership checks,35840 extreme legal
outputs and negatives for multiple wrong bits, both guards as one error, flags,
vstart, VL0 and20/21 DETAIL records. This is not a rerun or an independent full
enumeration of the generated model in this review.

`packed_core.h` has8 input SD,16 mask SD and16 output SD plus SH128, each volatile
asm with memory clobber. All arrays are aligned8; writes cover a/b0..31,
mask0..127, output0..129 with no typed alias cast. LHU/FMV.D.X stays in the
unchanged helper; storing four-halfword packets does not box raw b[0]. Immutable
input periods are uint64 objects, not aliased uint16 arrays. All shift widths and
unsigned intermediates are bounded; result extraction is16 bits, status checks
retain the full low/high32 distinction. Output LWU reads bytes0..3 even on a bad
status; uint32 extraction prevents high-bit sign-extension from altering guards.

The clear-lowest-bit loop adds one error per wrong bit and does not early-exit
the call loop. Combined guard OR and the unchanged `errors!=prior && details++<20`
preserve original diagnostic counts/fields. Explicit source unboxing and fixed
DK0 old remain distinct from alias-m8 behavior.

Actual lowering obligations remain open: prove41 stores and the LWU in linked
code, original helper bytes/no extra RVV, correct caller preservation of record
and flags, stack/map and whole CFG cost. The eight immutable input loads are
ordinary const C reads: source-level memory clobbers on stores do not by themselves
prove eight dynamic LDs each call. If that load-site contract is retained, verify
it in actual code before admitting a checker; never infer it from the Python model.
Do not charge an unobserved load as measured, or silently relax source freshness.

The 2967200 planning figure remains unproven. Neither model PASS nor this source
review admits a3M reference run or<=3h DUT run. The e32 terminal observer was not
queried or modified.
