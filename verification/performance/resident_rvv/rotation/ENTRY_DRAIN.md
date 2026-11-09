# Resident ownership entry: observed old-instruction drain

The accepted rotation-control trace was rechecked before planning native issue
exclusion. This is an offline analysis of measured RTL lifetimes, not a new
simulation or an assumed constant ownership latency.

Evidence: `ara_dsa_signoff_integration/verification/out/resident_pv_entry_drain_20261108_01.json`.
The analyzer checks the original accepted receipt, vector trace hash and original
attribution artifact hashes. It reconstructs each allocated VID through its
matching completion and rejects missing/reallocated identities. Two small host
tests check empty sets and allocation/completion edge conventions.

| Measured workload | Sample points | Older live VIDs | Remaining whole cycles |
| --- | ---: | ---: | ---: |
| Native auto, PV helper entry | 6 | 0 at each | 0 at each |
| Rotation-and-loop control, PV helper entry | 6 | 0 at each | 0 at each |
| Native auto, first PV row allocation | 6 | 0 at each | 0 at each |
| Rotation-and-loop control, first PV row allocation | 6 | 0 at each | 0 at each |

There are four complete calls (ABBA), each with T=64,64,9; all use D128/H2.
Helper entry and first row are two observation points per tile, not independent
workload cases. `alloc < entry < done` defines an older still-live instruction;
completion at the entry edge adds no remaining whole cycle.

## Consequence for integration

The tested scheduling does not rely on overlapping older vector instructions
across PV entry. A conservative older-VID drain gate is therefore a reasonable
first integration choice. It avoids changing dependency rules merely to acquire
the FPU. It still needs an actual complete-call timing test: importing operands,
native pipeline/operand drain, arbitration and ownership registers are not free.

This observation does **not** prove the FPU or every operand queue is empty.
No fixed delay, VID-only readiness or timeout should authorize borrowing.

## Concrete source constraints

- `lane_sequencer.sv` has a fall-through PE-request register and a registered
  `vfu_operation_valid_o`. Its public `pe_req_ready_o` can acknowledge entry into
  that register before a native operation reaches the VMFPU. Merely masking
  `mfpu_ready` at acquisition is insufficient and can strand earlier operands.
- `ara_sequencer.sv` allocates load-like requests in the load PE and enters
  `WAIT`, preserving the original request until address/operand acknowledgment.
  A resident command should use a blocking completion contract, with its final
  acknowledgment generated only after resident computation and all final VRF
  write grants. A private SRAM replay acknowledgment is not that terminal.
- Existing `WAIT` records per-lane source acceptance. A new source-bearing
  command must retain that bookkeeping, not use `no_src_vrf` to bypass import.
  Source geometry and destination geometry remain different.
- Older VID completion, registered request/operand drain and VMFPU endpoint
  acquisition are separate conditions. Global exclusion must keep younger
  native operations out until every lane has released resident ownership.
- Lane result acceptance and final write acknowledgment are distinct. The
  group barrier prevents precommit partial writes; the parent still needs an
  outstanding-final-write count before CPU completion and context release.

The new cluster protocol gate addresses the last requirement using real PV lane
controllers. It does not yet implement the decoder, source import or sequencer
exclusion above. These must be verified in the eventual SoC gate before runtime
capability is exposed. Other dimensions and concurrent scheduling must not be
claimed covered by this D128/H2 trace.
