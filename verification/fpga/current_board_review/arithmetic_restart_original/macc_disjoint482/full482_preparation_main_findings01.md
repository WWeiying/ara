# Complete482 Preparation Findings

These findings concern verification preparation. None is evidence of a new
VMACC RTL fault; the failed stages did not launch DUT or a new reference.

## Root Causes Checked By Main

1. Python compatibility: `zip(..., strict=True)` is unsupported by the selected
   interpreter. Explicit length equality followed by ordinary zip preserves
   the full-scope comparison; do not drop the length assertion.
2. RNG false positive: source insertions shift absolute character offsets.
   The initial comparison applied the original source offset to transformed
   text. Main's read-only minimal witness shows offsets7641 versus7773,
   old absolute slicing unequal, and independently anchored RNG bytes equal.
   The corrected actual transform proof also records identical RNG hashes.
   This is not a reason to change the model, random sequence or inputs.
3. C message escaping: the generated `MACC_OPT_RNG_FAIL` message contains an
   actual newline inside a C string. The compiler reports an unterminated
   literal. Correct only producer escaping and syntax-check final C before
   costly target/reference stages; preserve the original failed artifacts.
4. Source/output path confusion: the work04 successor changes `HERE` to its
   output directory but still resolves `host_adapter.c` through that variable.
   The actual compiler error is a missing file, not a C semantic failure.
   Audit all immutable input paths separately from new output paths before
   proceeding, rather than discovering each omitted file by another compile.

## Scope Must Remain Unchanged

Retain all482 original calls and481 predecessors, all accumulator patterns,
RNG order, full512 result bytes, physical mask128, both guards and status
checks. The last scalar word may load additional allocated bytes, but the
oracle must ignore bytes outside the original result/guards. The existing
negative test deliberately permits corruption beyond the guard; removing
that permission would silently strengthen the original oracle.

Preparation acceptance requires actual Host execution and source/optimized
full-call equivalence, not merely successful syntax checks. A bounded Spike
and reviewed frozen-M8 checker remain later gates. All earlier preparation
failures retain their original logs and exits; no failed record is relabeled.
