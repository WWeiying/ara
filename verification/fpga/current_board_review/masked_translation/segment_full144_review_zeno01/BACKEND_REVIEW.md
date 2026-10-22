# Full144 Backend Presence Review

Focused decision: the reviewed checker6b6269215c83b70eb73cac01411731e7eec945ffb497278e7ec6bd7acdd75e2b closes the identified whole-owner-pair false positive. This is not full worker entry approval.

## Static Requirement

- Frozen M8 ara_dispatcher.sv:5968 elides requests for VL/vstart or specific decoded no-op conditions, not a predicate value pretest.
- segment_sequencer.sv:204 and :232 issue element/field requests without an all-off predicate input.
- ara_sequencer.sv:854 and :885 allocate masked memory backend and MASKU lifecycles before predicate consumption.
- vlsu/addrgen.sv:626 and :926 read the real owner-qualified mask; an inactive element then enqueues is_skip at :935. No AXI request is not equivalent to no backend owner.
- Therefore every successful VL>0 target, including all-off, requires backend ownership/completion. VL0 may be elided; an actual target exception may be early-elided. Staging, mask loads and readback remain necessary independently.

## Independent Boundary Evidence

probe_backend.py uses actual archived-helper ELF opcodes and the real frozen M8 generic validator, with synthetic event ledgers. Actual process exit0, six probes:

- Two staging owners: generic and strict accept.
- Delete one entire staging alloc/done pair while another remains: generic accepts alloc=done>0; strict rejects.
- Delete a successful all-off VL1 target pair: generic accepts; strict rejects.
- All-off VL1 target pair present: both accept.
- VL0 target without a backend pair: both accept.
- Eligible actual-exception event at target without a backend pair: both accept.

These prove event/backend gate boundaries only. No manual fixture memory put, full Checker.row traversal, full144 dynamic positive, vector payload or DUT execution is claimed. A real capability outcome still requires the independent complete context/target/cause/phase checker; this probe does not waive it.

analyze() now invokes backend_coverage() after finish(); audit_job() calls analyze(). Thus the strict gate is consumed, not merely an unused helper. No speculative fixed total uop count was added.

## Separate Metadata Blocker

The source-review record correctly retains its historical main-review SHA f6c02707df51dcd5ff711dd5e690174ba2ad8597d417b93b2d48ce4f86f58d0d. The shared segment_full144_main_review01.md now hashes28c2c5904172343205b3f8a0ac10f0844182f51238aec65a1e97bee61fe04165. Current source_review() verifies the historical hashes dictionary, so this exact provenance gate rejects. Tesla was notified before launch: use an explicitly reviewed source-review successor/addendum and narrow successor consumption; do not edit sealed inputs, restore main's file or fabricate the old hash. No new raw parse is needed for this documentation-only dependency change.
