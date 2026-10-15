# Exact Entry Failure-Path Qualification

Decision remains NO_BLOCKER for the current entry SHA
41b945d40245cbb661d0ff8b014250e155d80c790eb0e97b32a274c974de72a2,
one bounded reference only. This note qualifies the actual unchanged assets;
it does not modify the entry or weaken any acceptance predicate.

## Exact Omitted Instructions

Paths below are under arithmetic_restart_original unless stated otherwise.

| Source condition | Spike omitted PC/code | SoC omitted PC/code | Actual incoming branch |
| --- | --- | --- | --- |
| full_e64_m4_block_prepare01/software02/case.c:94, cap!=64, unsupported text and return2 | 80001c5e/00001797 AUIPC a5 | 80001c72/00001797 AUIPC a5 | Spike80000368;SoC80000360, capacity-failure arm |
| same case.c:167, errors!=0 selects FAILED rather than PASS text | 80001c96/00001617 AUIPC a2 | 80001caa/00001617 AUIPC a2 | Spike80001b0e;SoC80001b1e,BNEZ after loading errors |
| full_e16_mf4_prepare01/runtime/runtime.c:36, number!=64 OR fd!=1 OR length<0, SERVICE_FAIL and exit126 | 800023f6/1141 C.ADDI sp,-16 | 8000237e/1141 C.ADDI sp,-16 | Spike800023aa/23b0/23b4;SoC80002354/235a/235e |

The runtime source above is the exact one in software02/spike/compile.log.command.json,
not an inferred runtime version. Normal text uses syscall3(64,1,pointer,n)
at case.c:38, with computed nonnegative length. The third row is its error arm.

## What Changed and What Did Not

No ELF, firmware, helper, oracle, derived spec, checker or pin changed during
this independent review. The shared reader in compiled_audit01/inspect.py:21
uses a mnemonic followed by \s*([^\n]*). For operand-less RET, \s* consumes
the newline and makes the following instruction look like RET's text operand.
Each omitted instruction follows such a RET. Independent read-only inventory
used horizontal whitespace to recover2862 Spike/2832 SoC code records, versus
the sealed specs'2859/2829. This was a correction to this review's inventory,
not a production or sealed-asset fix.

Two earlier producer changes must not be conflated with this omission:

1. compiled_audit02 ->03 added only the predecessor-AUIPC inclusion at the
   comparator's checks-address entry; old audit02 rc1 remains. SameELFs.
2. Before entry seal, lifecycle completion moved from enter to post-effect
   leave, with the same completeness predicates. Old Host01 rc1 remains;
   final Host03 actual26PASS binds the corrected source. This was a real
   checker bug, not a change to input/output expectations.

## Acceptance and Diagnostic Impact

reference_entry01/reference_check.py:55 checks code.get(pc)==insn on every
firmware retirement before processing that instruction. Any omitted PC fails
immediately. None can be silently ignored or treated as PASS. Additionally,
capacity64, original failure-routine rejection, exact software exit0, full
console/counter validation and complete oracle are unchanged. There is no
positive path through these failure arms in the source-faithful successful run.

The real limitation is reduced failure diagnostic fidelity: a bad argument or
error path can stop as PC/code mismatch before its original failure message.
This is fail-closed, not a relaxed oracle and not complete all-code-map coverage.
It does not justify a new reference retry. If later repaired, use a fresh
successor with new pins and small explicit rejection tests; preserve this seal.
No new negative tests were executed by this review.

## Stack and Cost Level

Only the replay_write error-entry instruction allocates an omitted frame:
16B. Including this static failure frame gives568B Spike and520B SoC for the
sum of all observed negative stack adjustments, correcting552/504. This sum
is not an actually simultaneous call-stack high-water measurement. Main's320B
frame is unchanged; BSS-to-stack gaps764056/772576B remain far above64KiB.

All three omitted instructions are outside the successful path. Its bound
2863981 and136019 headroom remain unchanged. Failure-path runtime was never
bounded by that number. Reference numeric wait/fullraw checks remain required;
this review is no reference result, no DUT PASS, and no VCS authorization.
