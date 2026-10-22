# Four-Case NF2 Sv39 Reference

Terminal update: the separately parent-authorized candidate02 DUT run passed
all four cases and 4133 checks. Exact identities, trap/field/checkpoint evidence
and independent pin recheck are in [DUT_REPORT.md](DUT_REPORT.md). The reference
and preparation-stage history below remains unchanged.

Owned adapter only. No production RTL or sealed extended8 sources are edited.
This runner builds host, SoC and Spike ELFs and runs host/Spike only. It has no
VCS launch path. Software reference acceptance is not RTL acceptance.

## Scope And Provenance

Original source identities and Linux oracle: `../SELECTION.md`.
`reference*/linux_provenance.json` pins original source C/S, case.json and ELF,
including original full-sequence ELF versus the trace and failing single ELFs.
`input_pins.json` also pins the adapter, tools, imported helper, inspected
extended8 source and immutable integration startup/runtime/linker inputs.
`prepared/provenance.json` pins the six files actually compiled.

| ID | Archived tuple u/s/b/m/f | Historical status | Base relative to P |
| --- | --- | --- | --- |
| 0 | 0/0/3/2/1 | Genuine failing load single, errors=1 | P-14 |
| 1 | 0/1/3/2/1 | Genuine failing store single, errors=1 | P-14 |
| 2 | 0/0/5/2/1 | Passing selected full-trace load trial, errors=0 | P-22 |
| 3 | 0/1/5/2/1 | Passing selected full-trace store trial, errors=0 | P-22 |

All four retain e16m1, VL8, tu/mu, v24/v25, mask bytes0x24, NF2 unit segment
instructions and source data formulas. Initial vstart=0; expected fault/retry
vstart=5. P=0x40001000, mapped VA base=0x40000000. b3 must not fault at inactive
segment3. b5 faults on field1 while field0 is accessible. Exactly one page
fault and one terminal supervisor ecall are expected per case.

The Linux PROT_NONE/signal-frame path is adapted to the proven extended8
invalid-leaf Sv39/M-mode handler. This is an explicit semantic derivative,
not execution of the original Linux ELF or verification of Linux signal ABI.

## Oracle Contract

- Real S-mode target opcodes are exactly 0x20055c07 / 0x20055c27; the same target
  PC is retried after addressed SFENCE and restoring vstart5. Target access
  lists exclude every inactive element and completed prefix on retry.
- Capture full v23/v24/v25/v26 before repair and after completion; neighboring
  registers, snapshot guards, both full data fields and tails are checked.
  The original load oracle leaves faulting segment5 unconstrained at trap;
  only these two halfwords are omitted from that snapshot check, never from
  final checks. The store source registers are checked without exclusions.
- Full two-page memory is independently predicted before repair and finally.
  Only b5 store field0 at fault may be original or its specified input value.
  No observed value is copied into expected final state.
- Repair the protected leaf and poison ONLY completed active element2, both
  fields, using original XOR0x5b (load) or input XOR0x5b (store). Final prefix
  register/memory results distinguish correct restart from accidental replay.
- Check both 64-element output fields and guards, mask source, all 1536 page
  table entries, surrounding page guards, precise trap records and untouched
  later marker at fault. Check terminal CSRs and restoration of saved machine
  state. A failed case stops before next-case memory initialization.
- Original b3 fault-address oracle permits either protected field of segment5;
  Spike's ordered access log is checked separately. b5 requires exactly P.

Python independently reconstructs vectors and memory, cross-checks host C
oracle rows, and reconstructs memory from Spike committed writes at all eight
checkpoints. It verifies exception and repair/retry/younger ordering, rather
than accepting the firmware PASS string alone. Deliberately corrupting prefix,
field1 tail/data, neighbors, guards, PTEs, mask, PC, vstart, partial store data
and younger marker must fail the checker. Explicit legal partial-field states
must remain accepted. Negative checks are software checker tests, not RTL runs.

## Run

```sh
python3 verification/fpga/current_board_review/masked_translation/segment_review/sv39/reference.py \
  --out verification/fpga/current_board_review/masked_translation/segment_review/sv39/reference01
```

Output directory must be fresh. ISA is recorded explicitly as
`rv64gcv_zfh_zvfh_zvl1024b`; compiler is the existing RISC-V GCC, not ZCC.
Spike has a 90-second process bound and a 2.5-million committed-instruction
acceptance bound. Firmware prints only its terminal marker or first mismatch.
The host oracle text and Spike commit trace stay in the output directory.
