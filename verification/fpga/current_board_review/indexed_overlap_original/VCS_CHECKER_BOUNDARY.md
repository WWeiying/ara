# What Transfers To A Future VCS Observer

This is a preparation review, not a VCS adapter or permission to launch.
`check_reference.py` accepts Spike commit text and **must not** be applied to
CVA6 CSV by relabeling its input or accepting missing observations.

## Reusable Oracle

- Exact 50 checkpoints (51 for resident including original masked restart),
  all 32 scalar copied results and both guards at every checkpoint. The C wrapper
  adds `io_result` scalar stores precisely so the real CSV can observe each value
  independently of unreported vector memory effects. `check_point` is reusable.
- Actual helper instruction bytes and exact target PCs from each SoC ELF's own
  disassembly; do not use Spike ELF PCs for the SoC ELF.
- 50 original index-load prologues, plus one masked helper prologue for resident;
  no index reload between a fault and its successful same-PC continuation.
- Fault record stores and corresponding CSR reads: cause13, mepc, mtval, vstart,
  VL32, vtype17, fcsr117, vcsr5. For the chosen fixture policy, 32 faults/round,
  starts0..31, PTE update/addressed SFENCE/MRET and unchanged PC.
- `io_exit_code==0`, errors0, exact round/map/unmap/fault counts and final magic;
  exactly one original VECTOR_PASS and one INDEXED_ORIGINAL_PASS; every FAIL,
  runtime trap, timeout, abort or unsuccessful process/CTRL exit vetoes PASS.
- Input/ELF/runtime/image identity and source manifest checks remain separate
  gates. A prior reference PASS is not an image or DUT acceptance.

## Required CSV-Specific Work (Not Implemented)

Reuse the proven NF2 `csv_check.py` scalar-store decoder read-only: CVA6 RVFI
reports shifted byte enables and unshifted source register data. Validate
PC/opcode, scalar register source, address, width and mask before reconstructing
`io_result`, trap records, counts and PTE stores. Host-negative the new observer.

The proven CSV does not retire the faulting vector target. Spike's 1650 target
attempt count therefore cannot be imposed on CSV. For each fault program expect
50 successful target retirements plus 1600 measured handler fault records,
associated repair/SFENCE/MRET and 50 prologues. Establish exception identity from
handler CSR reads and their stored records, not an invented retirement event.

Spike's `mem` list exposes actual vector accesses; existing CVA6 CSV does not.
The CSV can verify the complete final scalar-copy result oracle, but cannot by
itself prove per-element pre-fault VRF write timing or raw index operand data.
Use the bounded signal plan for those questions, only if a DUT measurement
requires root-cause evidence. The per-iteration copied result is stronger than
just checking the terminal firmware string but is not a cycle-level VRF probe.

All backing-memory and page-table firmware checks remain enabled. CSV can
observe their scalar reads/comparisons and scalar PTE stores; reconstructing only
scalar stores is not enough to detect an unobserved illegal vector write.
Require actual firmware checks/final full-memory checksum result, not a pristine
store-only shadow-memory assertion that could miss such a write.

## Known Limits

Linux memfd/minor-fault batching, signal frames, scheduler/context save, original
VA and historical exact failing round/start are not reproduced. Source and helper
equivalence plus successful Sv39 references establish a bounded faithful math/
instruction port with an explicitly different fault schedule, not Linux closure.

This fixture makes no software vector snapshot in the trap handler, deliberately
avoiding perturbing EEW metadata or reloading indices. Prefix VRF bytes at the
fault remain a waveform question. A source snapshot-valid clear without the
request/write/exception/retry chain is not sufficient root-cause evidence.
