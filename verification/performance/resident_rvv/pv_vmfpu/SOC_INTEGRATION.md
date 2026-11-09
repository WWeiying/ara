# Parent integration obligations

The VMFPU endpoint is not a complete resident instruction. The following are
required before enabling it in the lane/SoC wrapper.

1. **Drain the registered instruction path, not just the FPU.**
   `lane_sequencer` registers `vfu_operation_valid_o`. A native instruction can
   therefore have passed upstream readiness but still be in transit when the
   local VMFPU looks empty. The parent must stop new native issue and drain this
   register before asserting acquisition. Local priority for a simultaneous
   native offer only protects the offer already visible at the VMFPU input.
   A test that holds a native offer while owned does not prove this upstream
   pulse has been preserved.

2. **Account for operand requests outside the VMFPU.**
   The endpoint checks input valids, native instruction queues, result queues,
   reduction traffic and FP flags. It cannot see a request already in the VRF
   requester or an empty operand queue that will receive a response next cycle.
   Ownership must include the corresponding requester/queue drain or a parent
   reservation preventing those requests from entering this path.

3. **Reserve independent source and destination geometries.**
   The proposed coefficient/seed import consumes six registers but the largest
   paired PV result occupies four. Existing QBACC geometry cannot be reused by
   changing only `vl`. Source reads, EMUL alignment, source hazard masks,
   destination hazard masks and write masks must agree explicitly.

4. **Keep private payload transfers distinct from architectural VRF writes.**
   An existing LDU data wire may carry private values under a qualified owner,
   but its private ready handshake must not look like an architectural write
   grant or retire an ordinary load VID. Per-lane acceptance must prevent
   duplicate delivery when only some lanes are ready.

5. **Hold an all-lane commit barrier.**
   On a precommit error, cancel all private lanes and drain their accepted FPU
   work. Do not expose any destination write until all participating lanes are
   successful and ready. Once a write is irrevocably accepted, cancellation is
   forbidden even if final write acknowledgment has not yet returned.

6. **Complete the architectural contract.**
   Decode must enforce supported shape, register alignment, current FP state,
   rounding, and `vstart` restrictions before mutation. Publish combined active
   flags, finish writes, and retire exactly once with the original CPU request
   identity. Context refill/release is excluded throughout. Capability stays
   absent until the generated ABI, decoder, SDK and fallback selection agree.

The current wrapper ties the service inactive. That is intentional: passing
the real-VMFPU arithmetic/ownership gate does not satisfy these six obligations
or establish a complete-call performance improvement.

## Encoding and source-layout audit

These are integration proposals, not currently advertised instructions.

- All custom2 `funct3` values are occupied. A candidate extension is
  `opcode=0x5b, funct3=7, funct7=2`, preserving column/panel values 0/1.
  Decode it before the existing column-load branch.
- Use the instruction's `rd` field for the vector destination and `rs2` field
  for the vector source base; scalar `rs1` carries T-1 in bits 5:0, H-1 in bit
  6, D code in bits 8:7, with upper bits reserved zero. First-pass decode must
  not accidentally read scalar rs2 for that vector register field.
- Introduce a new capability query word, rather than setting a new bit in an
  old word: `akv_runtime.c` rejects unknown bits in existing word 2. Proposed
  `akvinfo(4)` returns zero when unavailable, otherwise enable bit 0 and profile
  version 1 in bits 15:8. Generate constants and encoder through the ABI JSON
  and generator, not ad hoc instruction literals.
- First-pass decode must classify the new command as FP and enforce FS/VS
  legality. Append the operation enum without changing existing values. The
  current AKV command enum has one spare encoding, but that alone is not a
  complete decoder or software contract.

For four lanes/VLEN1024, reserve v8:v15 and read six registers: 384 e16 elements,
96 elements or 24 words per lane. Each lane receives coefficient head 0 in
words 0..3, coefficient head 1 in 4..7, seed head 0 in 8..15 and seed head 1
in 16..23. A central coefficient collector must undo the native EW16 shuffle.
Head-major coefficient storage is not already paired by physical lane.

Use a fixed 128-element seed and destination stride per head. For D64/96/128,
each lane consumes 4/6/8 active seed words per head. Final word addresses are
`vaddr(vd) + 8*head + word`; packing D96 heads contiguously would be inconsistent
with this layout. Reserve all four destination registers; define their inactive
slots explicitly in the ABI before selecting a preservation or clobber policy.

Source reshuffle detection and maintenance bounds need VL384, independently of
destination VL256. Updating only the lane source request would leave dispatcher
maintenance covering too short a source group. Conversely, interpreting all
eight reserved source registers as consumed operands would over-read the
six-register import. These distinctions must be tested with non-EW16 prior
register layouts, alias rejection, short T, D96, and one-head operation.
