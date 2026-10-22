# Full682 Dynamic Checker Independent Review

Decision: **NO_BLOCKER_DYNAMIC_CHECKER** for the reviewed code hashes and completed Host/reference evidence. This is not DUT PASS, full17920 closure, or original Linux ABI equivalence.

## Verified
- Independent integer model matches all1536 original FP16 fixture pairs,682 ordered calls,698368 input halfwords,349184 allowed result-bit sets and all sticky/NV outcomes.
- Strict oracle dynamically binds complete128-byte mask,512-halfword A/B,130-byte output initialization; known source/base operands; exact eight helper parameters; original helper PC/order/multiplicity;64 complete output bytes, table masks/flags and both guards per call.
- StickyNV, boxed scalar half input, immediate vstart0 and packed status/restore sequence checked. Explicit observed bootstrap vstart write establishes known state; no unknown-vstart default. Fresh per-call m8 load payloads prevent stale VRF reuse.
- Real frozen-M8 validate_trace returns16 integer count fields and no status. Current composition uses this actual schema, not mock status=VALID.
- Exact CVX-request and arch_start instruction sequences bind retired source offloads; transport/architectural/retired counts match, no replay/exception. Generic pairs transaction IDs and backend VID/order/insn completions. Every source operation needing backend execution must have an allocation.
- Independent real-CSV microHost rejects5 lifecycle-valid corruptions that generic alone accepts: missing allarch/uop, missing a complete backend pair, dropped whole instruction packet, duplicated balanced packet and reordered packets. This is protocol discrimination Host, not DUT evidence.
- Existing full682 Host4 tests preserved; current successor Host3 tests and actual worker Host7 tests have zero errors/failures and matching currentcode pins. Includes output/guards/flags/vstart, drop/duplicate/interior/order, stale load and unknown source; actual frozen parent monitor0/17 and timeout-negative durable outcomes before postcheck errors, late abort/plan/membership.
- Dynamic producer reference actual rc0/4.152s, audit96.304s:682 calls,12592 helper instructions,349184 resultbits,1364 guards,682 flags/vstarts,6141 offloads,min3306 backend arches; input/raw pins unchanged. Reviewer hashes/metadata-checks this evidence but does not repeat its rawparse.
- Private immutable template globals checked/rebound for actual NAME/jobs1/10800s; numeric-first monitor preserves actual first return before metadata/checker exceptions. Earlier constant-binding suspicion is withdrawn: template already imported currentnewscope; explicit binding now removes ambiguity.

## Limits
No new DUT/Spike/build run was started by this review. No owner/sealed source files changed.
Existing once-only user authorization may proceed only after actual preparedplan/dryrun/source/image/resource gates pass; no automatic retries or budget extensions.
The review binding is in this independent directory. Hilbert may copy the exact binding into its expectedentry_binding path; reviewer did not modify his files.

Evidence: model_evidence.json, protocol_evidence.json and entry_binding.json. Scope remains first682, not fullparent/Linux ABI.

