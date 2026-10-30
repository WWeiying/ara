# Shared Reader SoC Handoff

The accepted integration receipt is
`verification/akv/results/shared-reader-handoff-20261025.json`, independently
rechecked from `verification/out/shared-reader-handoff-20261024-01/`.

The private snapshot contains complete production QBS/AKV/VLSU modules with
one physical reader. Canonical `hardware/src` remains unchanged pending the
remaining fault and representative-workload gates. This is an executed SoC
integration, not the earlier isolated reader unit or compile-only top.

## What Passed

- The same sealed ELF executes six QBS and65 AKV commands, normal RVV before
  and after, one real QBS payload PMA fault, and subsequent retry.
- Software checks192 QBS output words and62 resident AKV rows, with guards,
  exact trap PC/cause/address, scratch-GPR preservation, external backing
  poisoning and QBS activation reuse despite a zero external activation base.
- Actual one-reader waveform checks all71 accepts/terminals, stable owner,
  command-accept counter reset, two-entry capacity, AXI-cut drain, context
  identity across the foreign owner and zero external reads for63 local
  AKV LOAD/RELEASE commands. Inactive endpoints must receive zero responses.
- Independent UVM/CVXIF/backend/AXI checking and before/after source/image
  inventories pass. Bounded FSDB output is exported and checked against the
  frozen shared-reader profile, with no fabricated dual-reader aliases.
- All71 command records are **identical field-for-field** to the audited
  dual-reader baseline, including busy cycles, traffic and diagnostic counters.
  This establishes no command-level regression for this synthetic fixture,
  not model-level performance or an area result.

The older baseline worker's FAIL status is retained. Its software/simulation
completed successfully; a corrected strict checker and independent wave audit
established acceptance without rewriting that history. See
`../reader_handoff/ACCEPTANCE.md`. The new integration worker uses the corrected
four-commit-word M1 contract directly.

## Opposite-Direction Fault Gate

`fault_main.c` and `fault_probe.S` add a different14-command fixture:

```text
normal RVV
QBS FILL
AKV FULL: eight Q rows, then K base0 -> PMA load-access fault
QBS REUSE with poisoned external activation and activation base0
AKV FULL retry, poison external Q/K/V, check all eight resident rows
QBS RELEASE, AKV RELEASE
normal RVV
```

Eight Q ranges exceed the reader's two-burst capacity, so the planner cannot
reach the invalid K range without older Q traffic progressing. The checker
additionally requires an actual Q-write pulse before the fault; the stimulus
shape alone is not treated as proof. The trap must identify the exact AKV
instruction, cause5 and tval0. QBS output is independently checked against
fixed finite results, and its saved activation is verified across the AKV fault.

The same new ELF runs independently on old and shared-reader SoCs. It is built
from the accepted GNU/startup/ABI closure and checked disassembly, not executed
through a reference substitute. Both workers pin source/image/tool identity,
collect bounded waves and require independent protocol evidence. CPU simulation
is bounded to600 wall seconds; no RTL or hint adjustment is part of this gate.

This gate is **pending** until both workers and raw rechecks pass. Program,
transcript and wave-checker unit tests are not substitutes for those runs.
The fault profile on the old image observes its real AKV reader only; it does
not relabel two readers as one or test general routing during QBS ownership.

Remaining integration gates include representative real-input QBS/AKV work,
MMU/AXI-fault coverage and promotion of the reviewed implementation. Held-AR
fault/drain has isolated-unit evidence but is not exercised by either SoC PMA
fixture. Unified payload storage remains separate work.
