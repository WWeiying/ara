# e64/m4 full 5,985-call software candidate: COST HOLD

The single authorized software build/Host execution completed with actual
wait exit 0 in 31.998270575422794 seconds. All 41 expected Host outcomes
matched. Both unchanged linked ELFs and the full source proof are in
`software01/`; its original artifacts and pins are retained unchanged.

Current linked-code inspection completed with actual tool wait exit 0:

- Mandatory success subtotal: **3,460,590 instructions**.
- Conservative complete success upper: **3,630,058 instructions**.
- Earlier 3,066,840 was a partial lower, not a whole-program bound.
- **HOLD:** no Spike/reference, VCS, RTL edit, or second compile performed.

These are static CFG counts, not measured retirement. See
`compiled_audit01/COST_REPORT.md`, `RESULT.json`, and `execution_receipt.json`
for the actual product hashes, instruction PCs, multiplicities, software
wait receipt, and complete cost breakdown. Independent Averroes review of
these current artifacts has been requested; it is not claimed complete here.

The one static proposal, `static_unroll01/PROPOSAL.md`, expands the eight
dictionary comparison blocks and exposes base reuse. All 66 volatile actual
and expected reads, XOR/OR, two-word tail, fallback, mask/FP events and full
history remain. Identified conditional savings are 365,085 instructions;
the resulting upper is still 3,264,973. This does not admit another compile
or reference. Output initialization already has 66 unrolled SDs.

Scope is the original 35 operations / three seeds / 5,985 contiguous calls,
383,040 results and 11,970 guards. Old resume03 board PASS is preserved as
historical evidence, not current-image acceptance or an unresolved RTL bug.
