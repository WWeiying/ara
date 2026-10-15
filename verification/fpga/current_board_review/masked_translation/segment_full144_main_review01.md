# Complete144 Segment Preparation Main Review

This review accepts deterministic scalar preparation, not DUT execution or
the archived Linux stall's root cause. The prepared e16/m2 source port covers
all original144 configurations in order, with NF3/NF4 unit/positive/negative
stride, offsets0/1, VL0/1/128 and active/all-off masks.

## Independently Executed Checks

Main verified the READY manifest link and all87 evidence-file hashes: no
missing or changed files. Using the actual compiled `software01/host.so`,
main poisoned all four buffers before each of144 resets and independently
checked all4718592 initialized bytes,18432 predicate bytes and1179648 positive
oracle bytes against two byte/halfword models.720 additional corruptions were
rejected: bytes0/63/64/8191 and nonzero returned vstart for every configuration.
The read-only checking process exited0; no DUT or Spike was launched by it.

An initial main command incorrectly treated READY's integer `pins` count as
a manifest dictionary and stopped before Host checks. The corrected command
reads the explicitly linked `evidence_pins.json` and verifies its hash. This
was a review-command schema error, not a source, reference or RTL defect.

## Required Outcome Separation

The actual reference reports120 numerical completions and24 original-allowed
target misalignment branches, with source exit77 and actual offline audit0.
This is complete capability evaluation, not144 numerical passes. Eligibility
alone must not predict an observed exception: the source allows correct
numerical completion for those same configurations too.

A capability branch requires actual target PC, direction-correct cause4/6,
offset1, VL>0, active predicate and phase1. Do not waive staging/readback,
scalar phase-store, page-fault, VL0 or all-off exceptions. Do not invent a
successful helper return or numerical readback after the terminated-child
branch. Preserve actual simulator exit separately from source exit77 and
the independently validated architectural outcome.

## Remaining Gate

The preparation uses real Sv39 but does not reproduce Linux clone/COW,
signal handling, scheduling or vector-context restoration. It cannot close
the recorded scalar phase-store/Linux stall. Final M8 worker admission still
requires actual RVFI addresses/byte-enables/data, fresh complete per-call
initialization, source-helper/CSR/fault ownership, all numerical oracle bytes
and paired CVX/backend lifecycle evidence. Use one bounded full144 run only
after those gates pass; do not substitute an easier prefix.

## Backend Event-Presence Follow-Up

Initial worker composition paired the observed uops and required a nonzero
aggregate count, but did not require each necessary architectural memory
owner to have a completed uop. Main flagged the possibility of deleting one
entire allocation/completion pair while leaving aggregate counts balanced.
The owner added `backend_coverage` and corresponding negative checks.

Main also reviewed successful all-off targets with VL>0. Current dispatcher
elides vstart>=VL, not a predicate whose contents happen to be zero. The
segment sequencer still emits field requests, and masked AddrGen emits skip
descriptors. Therefore a successful all-off target must not be exempted from
the completed-owner check merely because its mask is zero. VL0 and eligible
early-fault targets retain their legitimate distinct behavior.

A read-only synthetic main test using actual SoC target code and case3
(op0/VL1/all-off) omitted its complete uop pair. The revised checker rejected
it with `Actual memory owner has no completed backend uop`. No DUT was run.
This validates that specific checker negative, not an entire raw trace or
the historical Linux failure.
