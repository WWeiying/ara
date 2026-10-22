# Offline Checker Correction, No New Reference

The sole Spike run actually waited to exit77 in99.1460455s, no timeout,
666779691 raw bytes. Exit77 remains an original capability classification,
not numerical PASS. Original `reference01` failure artifacts remain unchanged.

The first checker rejection was at firmware record30830, before case0:
`PC8000044e / instruction f922 / C.SDSP s0,176(sp)`, actual address800fffe0,
actual full-width stored value0. The raw reader had no prior definition of
x8, so its `regs.get(8,-1)` substituted all ones and rejected an ordinary
main prologue spill. This is not a target, data-oracle, timeout or RTL failure.
Actual disassembly main begins8000044a; saved s0..s11 occupy its first
14 instructions. No initial GPR reset value is assumed by the successor.

The successor only learns an unknown initial callee-saved register from its
actual full64-bit write at the exact pinned main prologue PC/offset, machine
mode, before any case. Normal known-register writes remain strictly compared.
Outside that initial spill window unknown source registers still fail. Original
PC/code, full144 oracle, target-only fault rules, raw input and ELF are unchanged.
`test_spill.py` uses this actual observed fixture plus12 rejection variants.

A bounded prefix diagnosis stopped at that same first rejection; it was not
a second complete raw audit and did not execute Spike. The successor full audit
must preserve its actual process exit and pin all original inputs and this
correction. No original failure artifact is relabelled or overwritten.
