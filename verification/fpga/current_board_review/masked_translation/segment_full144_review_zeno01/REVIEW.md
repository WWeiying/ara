# Full144 Independent Source/Reference Review

Decision: **NO_BLOCKER_SOURCE_REFERENCE_SCOPE_ONLY**. Not worker entry or DUT acceptance.

## Evidence

- Actual READY `e62b7cff2bb0c583d8e5f1123439ea31df385e9576a2b222ec2ea985ef9b04d0` links an integer87 pin count to evidence_pins.json (manifest SHA35c8b41c...). Independently rehashed86 nonraw entries. The raw SHA88d81201.../666779691-byte witness is reused from main's verified manifest review, not a new independent raw traversal.
- Reviewed original source loops and actual helper disassembly: complete144 op/reverse/offset/VL/mask order, NF3/NF4, cap128, offsets0/1, VL0/1/128, active/all-off. capacity3 and eight helper lengths27/19/27/19/31/21/31/21 match actual original ELF encodings in both ports.
- Main's compiled Host.so poison/reset review covers4718592 initialization bytes,18432 predicate bytes and1179648 potential numerical bytes;720 additional mutations rejected. Existing preparation Host has7776 negatives. Reviewer did not rerun either.
- Actual fullparse02 wait is numeric0 /161.246s/no timeout; existing Spike wait is77 /99.146s/no timeout. Result schema and144 ordered targets/helpers/outcomes/traps match exactly, with288 checkpoints. Actual observed120 numerical +24 allowed target faults,983040 executed numerical bytes,96 no-active numerical cases.
- Every recorded capability context was checked against its real target/op, cause4(load)/6(store), offset1, positiveVL, active mask, phase1, S-mode/Sv39 and no successful return. All24 partial-status rows belong to those24 target faults. No target successor/return/oracle is fabricated.
- Observer recovery is narrow:12 unknown initial GPR values are learned only from the precise full-width main ABI spills. Wrong width/PC/register/mode/business stores remain rejected; this does not assert original Linux ABI replay.
- Original faulting helper preserves actual vstart/type/VL. Successful helper/post context is separately checked. Source restores saved CSRs, but reference's pre-main snapshot only checks already-known CSR values; no universal final CSR restoration claim.
- SoC/Spike stack gaps626504/618304 bytes exceed the unchanged64KiB reserve. Actual source proof disclaims full Linux binary equivalence and clone/COW/signal reproduction.

## Necessary Worker Rules Sent To Tesla

- Eligibility permits numerical completion; do not require DUT120/24 or infer a fault from offset1 alone. Require complete144 membership and case-specific observed outcomes.
- Only actual direction-correct target misalignment in phase1 is eligible. Staging/readback/scalar phase-store faults, page faults, VL0 and all-off faults are never waived.
- Source exit77/HTIF155 is capability completion, not simulator protocol SUCCESS or144 numerical PASS. Preserve actual simulator numeric receipt and exact raw failure/warning evidence; never broadly waive FAILED/Fatal or unknown outcomes.
- Require paired generic lifecycle plus necessary per-owner backend evidence with genuine VL0 elision semantics. Empty pending queues alone cannot detect deleting a whole alloc/done pair. Tesla's worker/checker remain unsealed, so this is a focused preparation recommendation, not a finding against a frozen entry.
- Bind source/reference outcomes as evidence, not required DUT counts. Keep reference audit's actual77 expectation reference-specific; do not mechanically reuse it as the DUT outcome oracle.

## Limits

No new Host, Spike, DUT, build or666MB parse. No author/RTL files changed. Original historical failing tuple remains unknown; this does not close the archived Linux scalar phase-store stall. Independent worker entry is separate after Tesla seals its actual plan.

Detailed hashes, actual schema and scope: `REVIEW.json`.

