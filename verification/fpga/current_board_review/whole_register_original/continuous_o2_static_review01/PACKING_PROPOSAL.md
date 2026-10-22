# Conditional Scalar Packing Proposal

Status: DESIGN ONLY, not implemented/compiled/reference-tested/admitted. Select
this one candidate only after the current O2 full-reference cost is complete
and its qualified continuous-DUT projection still exceeds10800s. Do not change
the current O2 files, rerun that reference, enlarge budgets or shorten1134.

## Preserve The Original Program

Keep seed/op/mode/start nesting, all1134 calls/366 skips, all20 assembly helpers
and inter-call vector history. Keep1024 input and1088 output bytes initialized
on EVERY call, both captured/returned vstart checks, complete1088-byte oracle,
the original error count and its first12 byte diagnostics. Retain DETAIL_BYTES,
source failure markers and actual return code. No reset partition or extra RVV.

## One Proposed Change

Use eight-byte scalar copying/comparison with explicit little-endian packing.
Input remains a64-byte-aligned byte array. A read-only3-seed by32-word table
(768 bytes) represents the exact `(i*37+seed*71+3)&255` period256; each call copies
all128 words using the corresponding seed row, repeated four times. Output is
fully initialized with136 words of0x5b5b5b5b5b5b5b5b. No cached initialization
is reused across calls. Table equivalence must be proved for all3*1024 bytes.

Check all136 output words in increasing byte-offset order. For each word:

- Outside the active interval `[32+start*bytes,32+n*128)`, expected is sentinel.
- Fully inside, load the corresponding eight bytes from CURRENT input,
  preserving the original oracle's post-helper source semantics.
- At a partial boundary, combine current input and sentinel with an exact
  byte-enable mask. Construct no shift by64; handle empty/full mask explicitly.
  Check address bounds before forming/dereferencing any input pointer.
- When the word differs, run the ORIGINAL byte comparison/diagnostic logic
  for those eight bytes in ascending order. Increment errors per differing
  byte, not per word, preserving `errors<12` at each individual diagnostic.
  Continue checking all later words/calls; do not replace full checking with
  a signature or first-error-only exit.

The active interval's bounds are monotonic and inside the original output;
start==evl means no active bytes. Prefix/suffix guards and prestart/tail bytes
are compared, not skipped. Output+32 and input geometry remain unchanged.

## C And Compiler Safety

Do not cast `uint8_t*` to `uint64_t*`. Use fixed-size `__builtin_memcpy` between
the byte arrays and local uint64_t objects, a legal byte-copy operation even
under strict aliasing. This is explicit GCC functionality, not reliance on
ordinary `memcpy` being optimized despite existing `-fno-builtin`. Preserve
`-fno-tree-vectorize -fno-tree-slp-vectorize`; do not use `-fno-strict-aliasing`
as a substitute for correct code. Do not assume the builtin emits ld/sd:
actual future ELF inspection must prove scalar code, unchanged helpers and no
RVV outside them. If it expands to slow calls/byte loops, reject this candidate
on static instruction cost before any new reference.

## Required Equivalence And Observer Checks

Before a separately authorized reference, Host-compare all1134 generated
inputs/expected output arrays and original skip/order/CSR arguments against the
unchanged C model. Exercise active/prestart/tail/guard and partial-word corruptions,
including multiple wrong bytes across two words and the11th/12th/13th error
threshold; compare exact total errors and ordered diagnostic fields. These are
Host checks of scalar transformation, not hardware results.

Relocate the observer from the actual new ELF. Require full per-call FRESH
write coverage for1024+1088 setup bytes, then136 nonduplicated normal-path
output-word reads, each expanded into its eight independently checked bytes.
The error-only byte fallback is not permission to drop or double-count normal
coverage. Bind all helper paths/arguments/status and real scalar address/width/
data, plus future CVX/architecture/required backend owners. Do not validate
output using only a model's shadow stores. A missing full initialization
interval, missing final word/guard or incorrect fallback count must fail.

## Cost Gate, Not A Speed Promise

The proposed setup becomes128 input +136 output word writes per call, and the
success oracle136 word comparisons:453600 word-level operations across1134
calls. Current source uses2395008 setup-byte writes plus1233792 checked output
bytes. This is an eightfold reduction in memory-operation opportunities, NOT
an eightfold runtime claim. Word address calculation, expected-value assembly,
loop/control, initialization-table loads and original vector helpers remain.

After the O2 reference reports actual firmware cost, identify the actual ELF
initialization/oracle loops and derive the candidate's static instruction bound
from their replacements. Require a supported under3h projection with margin
before requesting one bounded reference/one DUT admission. Do not apply
partition concurrency or arithmetic-program speedups to this continuous case.
