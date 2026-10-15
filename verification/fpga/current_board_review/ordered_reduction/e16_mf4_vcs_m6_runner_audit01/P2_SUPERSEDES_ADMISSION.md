# Plan01 Admission Withdrawn: P2 Scope Finding

This addendum supersedes the NO_BLOCKER conclusion in this directory's REVIEW.md
(SHA256 adf12d0ea582c606701f587f063cea52092db3919899fb9dd0fa0280f1469a07).
Plan01 a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e
is NOT CLEARED. Parent reports launch was stopped before execution.
The earlier review missed a real checker-scope hole; Host03 PASS does not
establish rejection of these extra architecturally retired operations.

Read-only consumption of the independent review confirms that the old checker
excludes only op_1/op_2 entry PCs. Their interior reduction PCs remain covered
by the whole-ELF opcode map but not by op_0's instruction count. Recorded balanced
CVX/retirement mutations pass the generic and full artifact checker:

- op_1 interior 0x80000754 / 14881c57 (vfredmin.vs).
- op_2 interior 0x800007a4 / 1c881c57 (vfredmax.vs).

Each has the original target plus one extra reduction while reporting one
target/21 helper instructions. The entry-PC control was correctly rejected.
These are two synthetic host-protocol proofs, NOT two actual DUT failures or
executions. This reviewer read/hash-checked the evidence, did not reproduce it.

## Preserved Evidence Identities

Paths relative to ../original_e16_mf4_vcs_m6_plan01/independent_entry_review01/:

| File | SHA256 |
| --- | --- |
| README.md | a20843773846beaa9cf944f185589d378db311bf9373e8c67c561246946448a7 |
| findings.json | 0e686d4f0569387be11bdc4f01629aba638919187a74e4a2605bb32c0bd8efe9 |
| extra_helper_evidence.json | ce3238d28c3a653983a71a580b069cfdf6435824533230b6356062f9e473ac9e |
| extra_helper_repro.py | b41ca3fbd842e770b084ddfb698c348fa8fc6bc1cb9d378e212bb693494b461e |

No old report, proof, helper, Host record or permission was changed. This is
an append-only identity record, not an assertion of filesystem immutability.

## Successor Review Boundary

Only a new plan02 may resolve this issue. Static review must check nonselected
helper full windows, op_0 execution window/exact21 sequence (including repeated
interior targets outside it), and explicit allowed RVV PCs/capacity counts.
Preserve legitimate original capacity instructions, vlenb CSR access, fractional
vset operations and all21 helper instructions. Do not reject all CSR/vector
activity outside op_0 indiscriminately, weaken byte data checks, or change ELF.
Original counterexamples and op_0-interior duplicate negatives belong to the
successor Host evidence; this reviewer will not execute old Host or DUT.

At this inspection plan02 directory was not yet present. No successor source,
Host or admission decision is claimed. Reference acceptance remains valid only
within its previously recorded single-source/actual-ISA scope.
