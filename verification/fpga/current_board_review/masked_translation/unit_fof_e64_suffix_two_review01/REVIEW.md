# E64 Masked Suffix Two-Single Independent Review

Decision: **SOURCE_REFERENCE_NO_BLOCKER_DUT_CHECKER_HOLD**.
Source/reference preparation is accepted in the scope below. The delivered
CSV checker is not ready for DUT admission until P1_OWNER_COVERAGE is closed.
No compiler, reference, DUT, or full raw-trace parser was run by this review.

## Blocking Finding

**P1_OWNER_COVERAGE**, `csv_check.py:121-123,233-237`:
`arch_start`, `uop_alloc`, and `uop_done` are recognized strings but immediately
discarded. The observer has no backend owner table or required-completion set.
Its final gate only checks one target CVX request/response plus scalar/helper
completion. Consequently a complete necessary backend alloc/done pair can be
removed without affecting its semantic acceptance state. The14 recorded Host
tests do not exercise this contract.

Independent tiny Host event checks on BOTH actual SoC specs accepted an invalid
opcode architecture event and an orphan done event. A balanced alloc/done pair
had no state effect other than rows/time. This is an observer counterexample,
not a simulated hardware failure or a fabricated full-trace PASS.

Minimal required successor: retain all source/ELF/reference artifacts; bind the
actual CVX and architecture instruction sequence to retired original offloads,
track backend order/VID/insn ownership, and require completed owners for each
necessary memory operation. For both selected cases, old-vd load, mask load,
VL8 target load/FOF and VL8 output store are all necessary; the target is neither
VL0 nor an allowed fault. Do not demand backend allocation for local vector CSR
or configuration operations. Pair the existing generic protocol validator with
this per-owner requirement; balanced-pair deletion can survive generic counting.
Add focused negatives deleting a whole required pair, wrong owner/opcode and
unmatched done, plus a valid tiny sequence. No new reference is needed.

## Source And Reference Evidence Accepted

- READY SHA: `816491edd10f338f435c3bcf473cb7cc4434d1ce65fbe7cfb419dab9bce6a2c5`.
- Rehashed all732 preparation pins, including610 frozen M9 image/source pins.
  Existing raw references were hashed only, not parsed or executed again.
- Original singles match the actual archive manifest and measured symptom
  records: e64 scenario1 ordinary masked load at0x10456, original ELF
  `25e13a67b7432e540269cca236a1b6596b66a0e152f121eb6f9ef8cc48ab0df4`;
  scenario2 masked FOF at0x1047e, original ELF
  `5538ce81a3a80a64ac089efb9c5f6dba84fc7e1bc13dc7e36c8253eb8479e85e`.
  Both actual board records report cause13/SIGSEGV at base+32. Neither has a
  preceding vector call in its archived round0 single.
- Independently read actual ELF PT_LOAD bytes: both original11-instruction
  load helpers and capacity3 match both SoC and Spike ports,50 instruction
  comparisons per scenario. This is helper identity, not Linux ELF identity.
- Original mask16 bytes, typed uint64 seed91,130-word allocation, four input
  words11/48/85/122, base page_end-32 and VL8 are preserved. Original output
  indices1..8 are11/48/85/122/91/91/91/91; original guards are0 and9. There is
  no undefined-suffix exemption and no repeated-byte seed substitution.
- Static fixture/independent oracle agree on complete data8KiB, page tables
 12KiB, all130 output words,16 predicate bytes and physical guards. Both helper
  return checks require immediate VL8/vstart0 before the original output store;
  later helper VL8 restoration cannot conceal FOF shortening.
- Only the completion S-ecall handler is accepted, after the complete helper
  and younger marker. Target CVX exceptions, target retirement faults, extra
  handlers and wrong trap cause/PC/vstart are rejected. No remap or retry exists.
  The invalid Sv39 second leaf reproduces the protected-address architectural
  condition, not Linux PROT_NONE encoding, fork/COW or signal-frame handling.
- Existing actual references each have child0,172731 records,5481 checks,
  one supervisor ecall, HTIF1 and no target fault. Full commit parse was not
  repeated; the producer's hash-bound raw acceptance is the reference evidence.
- Host14 and its numeric receipts are preserved. Their actual SoC exit tests
  use a real spec without `tohost`: `sd a0,0(t0)` at0x80000072,
  encoding00a2b023, CTRL0xd0000000/raw0; park at0x80000076. Actual ELF bytes
  were independently compared. HTIF1/nonzero17/wrong BE/address/source and
  premature/duplicate exits are rejected by the delivered Host tests.

## Worker Binding And Limits

`result.json` is machine-readable, with `source_reference_accepted=true`,
`worker_entry_accepted=false`, `DUT_admitted=false` and the explicit blocker.
`evidence_pins.json` binds the reviewed inputs and review script. It must not
be interpreted as unconditional no_blocker or parent launch authorization.

The successor worker still needs actual numeric child0 before postchecks,
raw failure veto, complete output/source checks, unchanged input/image pins,
sticky abort/no retry, actual terminal wait and the owner fix above. No claim
of zero physical MMU requests follows from architectural no-fault evidence.
No current DUT result or original Linux/full-parent closure is asserted.

Review process actually exited0 in2.235578s. This means the review completed
and reproduced the checker gap, not that DUT entry was approved.
