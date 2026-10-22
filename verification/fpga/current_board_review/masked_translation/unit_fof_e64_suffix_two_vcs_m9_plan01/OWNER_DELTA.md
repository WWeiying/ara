# Minimal Source-Owner Successor

The sealed source/reference remains accepted software evidence, not DUT evidence.
Its old csv_check.py remains unchanged. Tesla identified that it ignored
arch_start/uop_alloc/uop_done; aggregate generic balance alone could accept a
deleted complete owner pair. New source_owners.py adds only this missing gate.

Pattern reused: unmasked_strided_alignment_soc_m9_checker_successor01/checker.py
MemoryOwners. Monitor semantics checked against frozen M9 ara_commit_monitor.sv:
arch_start identifies a frontend owner, done precedes alloc for same-cycle VID
reuse, and backend rows retain architecture sequence, instruction and transaction.

Every row is passed unchanged to the sealed data checker and new owner checker.
Original source has exactly four memory sites: old-vd load, vlm mask load, target,
and result store. Each must have its matching architectural owner/request/
nonexceptional response/actual-PC retirement plus at least one completed backend
allocation. Additional maintenance uops are allowed only with correct owner.
Every allocation/done pair is checked by seq, instruction, transaction, live VID
and cycle. Pending/orphan/reused/wrong-owner events are rejected.

All four sites have actual VL8/e64m1/vstart0. The target is explicitly vm=0 and
the original mask is 0x0f followed by fifteen zero bytes: four active elements and
four inactive suffix elements. This is NOT an all-off target and cannot become
an empty VL/start no-op. Old full data/CSR/guard/PTE checks remain mandatory.

Host02: 44 worker/owner gates PASS, actual rc0. Tests cover each full pair deletion,
orphan done, wrong owner, empty VL, start==VL, incorrect all-off target, raw
partial FAIL, numeric-first0/17 preservation and late abort. These are artificial
owner rows/short host process, not DUT or repeated Spike/source reference.
Host01 failure is retained: string Path API mismatch at entry before runtime.
The only correction was new wrapper sha(Path(path)); no ELF/oracle changed.

Preparation/launch review should bind source_owners.py alongside checker.py,
replay.py, plan and the unchanged reference READY. No physical MMU request
suppression is inferred from CSV lifecycle or the future software PASS.
