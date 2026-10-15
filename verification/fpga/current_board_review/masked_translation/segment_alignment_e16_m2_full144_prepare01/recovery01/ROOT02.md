# Spike Partial-Status Row At The First Target Misalignment

The first successor audit stopped after17.415s, before completing a full raw
traversal. Its actual exit1 and error remain in fullparse01. No reference rerun.
Raw lines732780..732783 are:

```
core   0: 0x000000008000090e (0x4007dc07) vlseg3e16.v v24, (a5), v0.t
core   0: 1 0x000000008000090e (0x4007dc07) e16 m2 l1 c8_vstart 0x0000000000000000
core   0: exception trap_load_address_misaligned, epc 0x000000008000090e
core   0:           tval 0x00000000800630c1
```

This is an attempted target with a partial-status row, not a completed vector
instruction followed by a different instruction's fault. The successor admits
the exception only at the pending target slot or immediately after its own
status row, with no intervening firmware instruction. It then terminates that
helper window. No successor/readback/CSR-return instruction is invented.
The strict capability check still requires exact target PC, offset, positive
VL, active predicate, phase1 and direction-correct misalignment cause.
Partial-status rows are reported separately from completed numerical targets;
firmware cost is commit/status-record count, not an unqualified instret claim.
Negative tests reject wrong helper, PC, later slot or intervening instruction.
