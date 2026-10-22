# Closed-CSV Recovery Scope

Original plan11521664 remains sealed. Both actual simv children exited0;
original worker exited1 because strict checking indexed unknown x8 at the
first main c.sdsp. Old NOT_ACCEPTED_LATE_ABORT, aborted=true and the old
pins_unchanged=false field must remain unchanged. That field was not evidence
of measured input drift; a separate read-only check verified894 pins unchanged.

## Exact Opaque Inputs

Both original SoC ELFs use the same14 main-entry instruction encodings:
SP-=224, sd ra, followed by12 c.sdsp of s0,s1,s2..s11. Caller SP is independently
known from startup and must equal the real ELF __stack_top. Unknown callee
values may be captured only once, from actual RVFI mem_wdata at their exact
original PC, SP-relative aligned8-byte slot and byte enableff. No default0.
The first following instruction is the real mstatus save, outside this scope.

The real fx_handler has17 entry instructions: SP-=128 and16 sd of
ra,t0,t1,t2,t3,t4,t5,t6,a0..a7. Only t2/x7 and t3..t6/x28..31 lack an earlier
definition; both disassemblies contain only their handler saves and later
restores. a4/a5 are defined by initialization/checking, a6/a7 by the guard
initialization loop (sc0 PCs80000480/484/49a; sc3 PCs8000043a/43e/454).
Nested C check/fx_trap prologues save registers already known through the main
entry or prior real RVFI writes. No blanket handler/caller-register allowance.

Handler admission requires the actual retired completion ecall/trap at the
ELF fx_ecall PC, exactly completed original helper/younger marker, expected
returned VL, restored post-helper VL8/vtype24/start0, actual fx_enter_s SP,
and immediate next retired PC at fx_handler. Each of17 instructions must be
contiguous and match actual hashbound ELF bytes. All16 restore loads must use
their original PCs, registers, frame slots/byte enables, and exactly the saved
values; SP must be restored before the original MRET.

## Unchanged Checks

The original checker symbol keys were extracted via AST and checked against
both actual SoC specs. No optional/fabricated symbol, source change or oracle
change is introduced. All other unknown address/data-register uses fail closed.
The existing complete data/PTE/guard/CSR/FOF oracle, four nonempty memory owners,
source helper/capacity windows, unused-helper veto and actual CTRL exit are
inherited. Main and handler restore observations do not create extra DUT CSR
readbacks or substitute reference data for DUT observations.

Main-only Host12 and handler-delta Host10 each exited0 in under1 second. Their
logs/receipts are in host01 and host_handler01. Negatives include wrong/missing
address/BE, register, SP, frame, unknown business store, unknown a7, known-value
mismatch, absent/wrong ecall, replay/reorder and bad restore. Nonzero opaque
positive values verify that unknown does not mean zero. These are synthetic
checker tests, not new DUT/reference execution.

## One-Pass Admission

audit.py requires an independent NO_BLOCKER review binding five exact Python
files. It creates closed_audit01 exclusively, verifies old pins, actual numeric
child/monitor0, original command/privateELF and console veto, then passes every
CSV row unchanged once through the successor and inherited complete checker.
Old generic metadata is pinned and counts cross-checked, not falsely described
as independently recomputed. All input/evidence hashes are checked again after
the pass. Any failure is retained and stops; no automatic rerun. A successful
new architectural recovery never rewrites or relabels the old failed batch.
