# Comparison NV Ownership: Review Only

No implementation is proposed for immediate integration. Tesla owns VMFPU.
References below are to the **frozen image sources**, rooted at
`/home/wangwy/fpga_runs/current_board_integration_final01/frozen/sources`.
Live worktree line numbers/contents may diverge. `results.json` pins these files.

## Existing Boundary

- `hardware/src/lane/vmfpu.sv:2663` forces queued comparison `vm=1`.
  `:1831` builds issue BE; comparison restart does not use the ordinary
  VFU_MFpu restart qualification. `:1214,1227` supplies FPnew SIMD mask/tag.
- `hardware/src/lane/lane_sequencer.sv:428` balances MASKU preprocessing VL
  upward on every lane for nonmultiples of four. VL15 therefore includes a
  lane3 slot for element15 in the execution payload. Architectural tail
  qualification must be distinct from this transport count.
- `hardware/deps/fpnew/src/fpnew_noncomp.sv:261` forms comparison NV.
  `fpnew_opgroup_fmt_slice.sv:304` ORs masked per-element `lane_status` into
  one status. After this point aggregate NV cannot identify the offending
  element. `vmfpu.sv:1507,1545` forwards the aggregate flag before MASKU merge.
- `vmfpu.sv:1510` prepares element-spaced comparison results. The result queue
  and `:285` spill register transport a single 64-bit result payload to MASKU
  under ready/valid. No per-element exception sideband currently accompanies it.
- `hardware/src/masku/masku_operands.sv:225` compresses each result element's
  low bit using `eew_vs2`, `shuffle_index`, and `vrf_pnt_i` coordinates.
  Other result bits are not automatically part of that compressed stream.
- `masku.sv:774` calculates the exact packed `[vstart,vl)` window;
  `:825` applies architectural predication using `masku_operand_m_seq`.
  `:1454` gates accepted slice processing, `:1521,1531` retire result and mask
  inputs on their respective slice boundaries. These are not interchangeable
  handshakes. `:1708` reports instruction completion after commit accounting.

## Candidate: NV Beside Each Comparison Result

This avoids a second predicate consumer, but requires a new end-to-end contract:

1. Preserve each comparison element's NV before FPnew status collapse, or
   independently derive the exact comparison NV from classified operands and
   operation. A derivation must distinguish FEQ/FNE signaling-NaN behavior
   from ordered comparisons' quiet/signaling-NaN behavior, scalar boxing,
   and all supported formats. This is not an aggregate-flag fix.
2. Carry NV in lockstep with comparison data through processing latency,
   result queue and spill. Spare result bits are a possible encoding, not an
   existing interface guarantee; the EW8 branch already uses bit1 for a mask.
   Dedicated sideband versus payload encoding needs an explicit ownership
   decision. Any sideband must share the exact same stall/consume events.
3. Deshuffle/compress NV using the **same element mapping** as comparison bits.
   At accepted MASKU slices qualify NV with predicate (or unmasked vm), exact
   active window, and current-slice validity. Do not OR unconsumed or stale
   slots merely because they lie in the architectural window.
4. Suppress the old VMFPU comparison flag contribution; otherwise excess NV
   already reaches the CSR before MASKU can reject it. Keep other FP op flags.
5. Add a defined MASKU-to-architectural-fflags route. Current lane flags feed
   `ara.sv:242,492` and `ara_dispatcher.sv:1105,1115`; MASKU has no such port.
   Check flag visibility before busy/completion drops (`masku.sv:1708`,
   dispatcher `:1107`), reset, backpressure, multiple in-flight instructions,
   sticky preservation, and immediate CSR read/clear/write ordering.

## Alternative: MFPU Predicate Feed

Not established safe by the existing protocol. `lane.sv:216,228,240` routes
VFU_MaskUnit mask beats to ALU, not MFPU; integer comparisons still need ALU.
MASKU already owns the original predicate stream for merge. Merely unforcing
vm and routing MaskUnit to MFPU risks wrong consumers, duplicate consumption,
or deadlock. A viable alternative must demonstrate operation-specific routing,
one-owner beat accounting or explicit multicast with independent acknowledgments,
and preservation of balanced comparison result production. It also needs exact
tail/prestart element qualification, not only a predicate.

## Evidence Limit

The bounded architectural tests and scalar commit traces establish flag values
and instruction boundaries, not internal cycle-level causality. No FSDB or new
internal probes were used. Before choosing a repair, a focused capture should
bind accepted instruction identity, issue BE/FPnew SIMD mask, per-element raw NV,
result valid/ready, MASKU slice/predicate/window, and architectural flag delivery.
Do not merge this excess-NV family with the separately owned unordered-reduction
missing-NV failure.
