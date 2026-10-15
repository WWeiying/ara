# NF7 Full96 VCS Preparation

Preparation only. No VCS execution, image rebuild, production RTL change, fixture
change, archived-input edit, or subset substitution is authorized by this plan.

## Architectural Review

The accepted targets are ordered indexed NF7 e32/mf2, index EEW32, VL8. Each
field occupies its own architectural register v24..v30. At VLEN1024, VLMAX is
16 words. Under `tu`, words8..15 retain their loaded old values, and words16..31
in the same physical register also retain their seeded values: fractional-LMUL
unused space is tail, not disposable storage. v23/v31 guards and v16 remain
checked independently. No fractional-tail oracle is relaxed.

A trap in a segment permits a subset of that segment's fields to complete;
ordered indexing does not impose field-order atomicity within a segment.
The allowed tval set remains every protected field of the expected faulting
element, and vstart remains the element index. Fault-phase active load fields
at/after vstart are not promoted to strict intermediate gold. Completed active
prefix, inactive elements, tails, source registers, protected memory and guards
retain their original strict rules. Final fields and memory are fully exact,
including prefix poison after same-PC/vstart restart.

These rules follow the [ratified RISC-V V specification](https://docs.riscv.org/reference/isa/unpriv/v-st-ext),
sections on tail policy, prestart/body/tail definitions and vector segment
loads/stores. The accepted reference's exact within-segment access order is
Spike evidence only; it is not imposed as a hardware field-order requirement.

## Checker

`csv_oracle.py` accepts scalar RVFI, not invented vector memory transactions.
Vector-written ranges are invalidated until scalar oracle loads observe their
contents. It independently compares checkpoint bytes against the original
Python gold, and binds the complete sequence of scalar checks to accepted
Spike ledgers. It also verifies actual trap CSR reads against stored records,
permitted tval, PTE repair/SFENCE order, unchanged retry PC, restored vstart,
prefix poison, exact check/case counters, full-group magic and CTRL completion.
CSR restoration binds to this DUT's captured initial values, not Spike's reset
constants. Target PC constants are symbol-relocated, not loosened.

Firstfailure records include trial, phase, check count, last retirement/cycle
and completed checkpoints. UART and simulator PASS are still required through
the sealed runner; neither UART alone nor partial checkpoints admit PASS.

## Fixed Scope and Budgets

- Exactly 24 accepted ELF groups, four original trials each: complete0..95.
- Same candidate02 image ledger
  `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
- Sealed integration runner, one group per invocation, inner timeout2400s.
- At most four simultaneous group invocations. Each orchestration invocation
  has a separate2700s bound for teardown and extraction.
- Suggested independent service hard limit for jobs4:16800s, covering six
  worst-case waves plus600s. This is not a launch command or authorization.
- First observed CSV error cancels the unlaunched queue and terminates only
  this batch's owned active runner/simv descendants; process identities are
  checked before forced cleanup. No retry, timeout increase or follow-on run.

The worker uses filesystem append notifications and a process-completion pipe,
not periodic service/log polling. The existing sealed runner retains its own
timeout and simulator assertion handling. Cancellation can only act when an
error becomes visible in a flushed CSV block; no unflushed data are claimed.

## Gates and Provenance

`vcs_adapter.py preflight` requires all96 terminal reference PASS, immutable
accepted ELF hashes, original-source identities, prepared source provenance,
host checker positives/negatives, candidate02 frozen539 inputs/configuration/
compiled source manifest, parent3+10 PASS and extended8 PASS6227. It prepares
all24 DRY_RUN invocations only and pins their complete input chain.

A future worker additionally requires explicit `--authorize-run`, a named
terminal NF2 unit (MainPID0), and the approved arithmetic unit. Any active simv
outside that arithmetic unit is a refusal. Arithmetic reserves at most four
slots under the parent's declared four-job plan; NF7 uses at most four, total
at most eight. These are one-shot gates, never waiting queues. The unit names
must be supplied by the parent at launch; they are not guessed here.

Plan/ELF/reference/helper/image pins are checked before and after execution.
The worker reuses accepted SoC ELFs directly. All evidence remains source-derived
Sv39 validation, not replay or closure of the original Linux executable.
