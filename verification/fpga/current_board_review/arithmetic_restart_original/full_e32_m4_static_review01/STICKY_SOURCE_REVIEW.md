# Static Sticky Comparator Review

Verdict: NO_BLOCKER_SOURCE_ONLY_COST_NOT_ADMITTED.

Scope: `full_e32_m4_block_prepare01/static_sticky01`, source-only successor to software01. All 18 STATIC_BINDING pins freshly matched. No Host, compile, reference, DUT, or raw-trace traversal performed by this review.

## Existing Candidate Remains HOLD

The independently reviewed finish03 evidence remains valid: Host 46, actual compiled SoC ELF, numeric finish03 exit 0; historical wrapper/finish01/finish02 failures retained. Actual mandatory disjoint core is 3,283,395 instructions, already above 3M before remaining main/caller/startup costs. This proposal does not relabel that candidate or replace its evidence.

## Exact Source Delta

Only the eight repeated word comparisons and final word comparison change to the RV64 BEQ/LI sticky template; Host retains C comparisons. Output initialization, actual-read barriers, immutable dictionary, cache fill/tag, FP input stores, mask stores, fallback, helper source, and call order are unchanged.

`mismatch` starts at zero and is a read/write `+r` operand. Equal operands leave its previous value intact; unequal operands set it to one. Both inputs are consumed by BEQ before LI writes the output, so no early-clobber is required. A live cache value/tag cannot be clobbered contrary to compiler operand liveness. The local forward label skips LI only, never subsequent actual reads. Host C tests alone cannot establish RV64 lowering.

There remain 64 full-block actual reads and one tail read per call, including after an earlier mismatch: 389,025 reads across 5,985 calls. The tail at offset 512 covers element127 and the rear u32 guard within the 520-byte object. Legal memcpy accesses and volatile read-consumption barriers remain; there is no aliasing cast. Eight cache values and the tag are local; unconditional first fill prevents cross-call reuse, and each different full-block ID refreshes all eight values. The tail has an independent one-word expected load. Existing valid-ID/table bindings remain required.

## Cost Boundary For Next Artifact

Old lowering has 65 SUB, 65 SNEZ, but only 64 OR per call. Replacing those with 65 taken BEQ on the positive path suggests `(65+65+64-65)*5985 = 772065`, not 778050, instructions saved. Conditional subtraction gives 2,511,330 for the old mandatory subtotal only, NOT a whole-program upper bound or runtime measurement.

The next uniquely authorized compile must establish actual 65 LD, cache/tag control paths, expected dictionary reads, all new spill/reload/register-save costs, callers/main/startup and branch behavior. The old six callee-save pairs and seven ZEXT.B are not assumed eliminated. Whole actual CFG upper bound must be <=3M before reference admission; no parameter trials or budget increase follow from this source review.

## Identities

- packed_cache.h: `b105cea283ce1f1a65a3cff4b37c9913e8ed24c797de54fa1c0717a41c95b3ac`
- SOURCE_PLAN.md: `85a6cd10bd0d476cc19d1bca5db76b11de563bb2fe739acd7936028f78a06f92`
- STATIC_BINDING.json: `dbfb865a3cf5301f07f6c601adc5d3b18c4de0b9e8bd2661107f69415da5602b`
- Prior SOFTWARE01_FINISH_REVIEW.json: `f4a49abef6fa1512c754cfe5a3fc2cb761141ab77a376d2615d07d1d9fa071b4`

Read-only verification used JSON parsing and SHA256 of the 18 listed files; verification process returned numeric 0 with no mismatches. This review authorizes no execution; parent controls the next compile stage.
