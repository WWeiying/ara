# Single static proposal: fixed blocks with sticky mismatch

Status: SOURCE_PROPOSAL_ONLY_PENDING_INDEPENDENT_REVIEW. No compilation,
Host execution, reference, VCS, or candidate/header replacement has occurred.
`proposed_comparator.h` is not included by an executable. The previous
software01 ELF and COST_HOLD remain unchanged. This new proposal supersedes
only the proposed comparator algorithm, not any prior evidence or source.

## Exact change boundary

Expand the eight full dictionary blocks with constant offsets, then process
the two valid words of block8. Replace only the scalar comparator's OR-of-XOR
accumulation by a sticky boolean. Do not change the initializer, dictionary
contents/IDs, per-call inputs, mask, FP refresh, helpers, CSR handling,
returned-vstart check, counters, or mismatch fallback.

The comparator still reads all 66 actual words and all 66 expected words,
including after any earlier mismatch. Actual offsets are 0..520 by eight;
block8 reads actual offsets512/520 and expected offsets0/8 only. The last
16B contain result63 and the upper guard, not dictionary padding.
All accesses remain naturally aligned uint64 accesses to actual uint64
objects; no out-of-range pointer, byte-buffer cast, or aliasing shortcut.
Ordinal remains the original 0..5984, and IDs retain the existing <1986 gate.

## Semantics for every input, not only successful outputs

For word i, let E_i mean actual_i != expected_i. Initialize bad=0 once per
call. Each update sets bad=1 if E_i, otherwise leaves it unchanged. Induction
gives bad after word k = OR(E_0..E_k). Thus the returned boolean equals
`(OR_i(actual_i XOR expected_i)) != 0` for all 64-bit input values.

Two equal differences cannot cancel; a later matching word cannot clear bad.
Mismatches at the first word, final result, or final guard all return true.
The fallback still executes only after all 132 loads have occurred and
retains its original numerical/guard/vstart diagnostics. The Host arm uses
ordinary C with the same recurrence, not a source-derived expected outcome.
It is a proposed implementation, not a newly executed Host equivalence test.

## Why explicit RV64 scalar asm, not a pure-C lowering promise

Pure C `if (actual != wanted) bad = 1` is semantically sufficient, but GCC can
if-convert it back into XOR/SNEZ/OR or another branchless sequence. There is
no reliable <=3M lowering guarantee from that C text. The proposed RV64 arm
therefore uses the single prescribed instruction sequence:

```c
asm volatile("beq %[actual], %[wanted], 1f\n\t"
             "li %[bad], 1\n\t"
             "1:\n\t"
             : [bad] "+r" (bad)
             : [actual] "r" (actual), [wanted] "r" (wanted)
             : "memory");
```

Each actual and expected volatile load is a separate full expression before
the asm. The next word's loads occur afterwards. `memory` is a compiler
barrier, not a hardware fence or MMIO ordering guarantee. This scope is the
existing ordinary memory, same-hart scalar checker after its vector helper.

`+r` is essential: bad is live in and out even though the equal branch does
not write it. It may be initialized to zero only at function entry, never
inside the word/block expansion. The branch consumes both input registers
before the only write to bad. Therefore the normal read/write constraint is
valid without early-clobber; even legal register overlap must have satisfied
the incoming values. There are no hidden register writes, stack adjustment,
calls, hardcoded registers, or condition-code side effects. RV64 has no flags
register clobber here. Both branch paths fall through the same asm statement;
numeric local label `1f` binds to that statement's following `1:`.

The asm contains no memory operand, CSR, FP, RVV, trap, or fence instruction.
Its memory clobber prevents moving memory operations across updates. `li 1`
may compress to C.LI but remains one instruction; every successful word
executes BEQ and skips that LI. On a mismatch it executes both, then continues.
The compiler can choose registers and addresses around the asm, but cannot
replace the explicit BEQ/LI contents by a branchless comparison.

## Cost against the actual existing ELF

Baseline is `../compiled_audit01/RESULT.json`, SHA256
`c55f35e5dbf1e5f16d06c16ab65137d138b061c28db6ff353e25851900229c83`.
Its successful-path mandatory subtotal is 3,460,590 and conservative whole
upper is 3,630,058. The 3,066,840 partial lower is not used for admission.

| Conditional removal from current compiled CFG | Per call | Full scope |
| --- | ---: | ---: |
| Eight blocks' five loop-only instructions | 40 | 239,400 |
| Dictionary base reused across nine blocks | 16 | 95,760 |
| Tail row-ID address reused | 5 | 29,925 |
| XOR/OR combination replaced by equal-case branch | 65 | 389,025 |
| Total | 126 | 754,110 |

For the last row, 66 XOR + at least 65 combining OR become 66 BEQ on the
success path, conservatively saving 65. This does not count eliminated loads
or a mismatch fast-exit. Both versions still have a per-call accumulator
initialization and final mismatch decision. Current code has an additional
OR into its zero-initialized block accumulator; no extra saving is taken for
that instruction. Failure paths may execute up to 66 additional LI and the
unchanged fallback; the success upper is not a failure-path time guarantee.

Under all identified lowering conditions and with no new overhead:

- Mandatory subtotal: 3,460,590 - 754,110 = **2,706,480**.
- Complete conservative upper: 3,630,058 - 754,110 = **2,875,948**.
- Remaining budget for added instructions: **124,052** total.
- 20 added instructions/call would consume119,700, leaving4,352 for all
  other increases. 21/call would already exceed3M by1,633.

This is a conditional static cost proposal, **not an actual GCC upper**.
The asm fixes the per-word comparison sequence only. Hoisting may be lost
under register pressure/memory clobbers; input/flag moves, stack spills,
address rematerialization, final normalization, and changed linker relaxation
must be counted rather than assumed free. The existing 20,000 success-runtime
allowance stays in the baseline; it is not another savings pool.

## ABI, code growth, and exact future acceptance conditions

At each update, bad and the two scalar input values must be available in GPRs;
the current and dictionary pointers/ID base also remain live as needed. The
three operands do not create new ABI-visible state, but they can change
register allocation. `always_inline` avoids a new callable ABI boundary; it
does not prove the current 320B frame or spill traffic remains unchanged.

Unrolling increases text. The current comparator has 72 static instructions
in its reported region (12 setup +42 loop +18 tail). A rough ideal success
sequence after the two savings groups is240 instructions, plus66 LI present
in text but skipped on equal data: about306 static instructions. Relative
growth is roughly234 instructions, at most936B for those instructions alone;
surrounding address/branch relaxation and spills are additional, unmeasured.
Reserve 1-2KiB as a planning allowance, not a measured ELF result. Every
inline BEQ jumps only over its own LI, so its local displacement is bounded;
surrounding C branches may still change encoding. ROM/data are unchanged.

Before any later reference admission, an independently reviewed actual new
ELF would have to establish:

1. Full5,985 original calls/history and all458 helper instructions retained;
   no new RVV or changed source/FP/mask/CSR events.
2. Exactly66 actual +66 expected volatile loads for each success or mismatch;
   ninth block is two words, with no early return or missing rear guard.
3. Fixed scalar BEQ/LI updates with one initial zero and no other clear;
   constant-block paths, actual dictionary base reuse, and all added moves,
   spill/reload traffic and final normalization included in the new CFG.
4. Original fallback and diagnostics preserved; first/middle/last mismatch,
   two equal differences, later matches after an error, dirty/all-equal data,
   and guard faults remain discriminating Host checks, including load counts.
5. Complete success CFG upper <=3M with original6K-scale history, not a
   shortened scope, raised threshold, or assumed compiler optimization.

This turn authorizes none of those compiler/Host/reference executions. The
next action is independent static review of this source and conditional cost
accounting. Current executable artifacts remain COST_HOLD.
