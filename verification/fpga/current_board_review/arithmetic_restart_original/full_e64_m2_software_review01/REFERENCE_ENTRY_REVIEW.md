# Software02 Bounded Reference Entry

Verdict: NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT.
This exact entry may consume the parent's existing conditional authorization for one reference attempt. No VCS, compilation, retry or budget extension is authorized. No reference has been run by this reviewer.

Reviewed entry: ../full_e64_m2_reference_entry01/entry.json
SHA256: 498f9b98e68f87a2a2ceb5617ecf9af4afcabd4d69bc19d1a848fa572203781e
All 461 entry pins freshly match. The earlier software02 errors and final compiled audit remain pinned. Actual reference ELF remains dc746ebf6b5978f7901d923cc741747e7ce35bb1693fab3b70df0a5a11a7127c; no witness assembly is substituted.

## Reviewed Gates

- reference.py requires the exact independent review status and entry hash before exclusive reference01 creation. It invokes fixed rs4000000/quit, wall120s and RLIMIT_FSIZE768MiB. The offline child is bounded600s. Actual numeric wait results are fsynced before subsequent validation; timeout/nonzero or drift is not accepted, and an existing attempt directory prevents reexecution. Firmware through HTIF above3M produces HOLD, not READY.
- context.py consumes pinned full5985 source sequence, original seeds/input bits and the independently Host-proven dictionary. Scope remains 35ops/191520 results/11970 guards/5985 vstart returns/77805 helper instructions/203490 eight-byte output reads. No reduced prefix, host-float oracle or extra fflags claim.
- lifecycle.py binds complete ordered BSS initialization and 276 original seed stores. Each of1890 FP calls enters the actual constprop clone with the expected seed-only ABI; contiguous 83/81/83-PC paths, eight table reads and all64 ordered destination SDs are mandatory. No VL0/equal-data/previous-shadow shortcut is allowed. All2205 mask groups require16 SD clears over128B plus original bitsets. Output initialization is34 ordered SDs; subsequent oracle is34 ordered LDs over272B, including both full u64 guards.
- reference_check.py checks actual PC/instruction identity, capacity's three-instruction window, vlen-derived CAP32, bootstrap fcsr/vstart, full original13-instruction helper windows, actual arguments, CSR context and physical2 groups v8..9/v16..17/v24..25. Full result bits, scalar read values, failure entry veto, final counters and exact console must agree before HTIF success. There is no accepted helper omission or incomplete final readback.
- raw_boundary.py requires the exact reset-ROM prefix and firmware entry, one exact HTIF success write, and reads through EOF. Any post-success activity except the exact side-effect-free park PC0x8000007e/insn0xa001 rejects. End-of-file without completed success rejects. Offline pins and raw identity/digest are checked before/after the sole semantic parse.
- The five-test Host receipt records actual exit0 and test-reported0.543s; process wall time is unspecified and is not invented. Tests are explicitly constructed lifecycle snapshots, not executed full predecessors. They cover all three clone paths, equal-value deletion, swap/duplicate, missing VL0 refresh, missing fresh/output-tail access, upper mask/stale-seed violations, physical group width and extra post-success activity. These small tests supplement, not replace, the forthcoming actual full reference.

## Owner Scope Limit

source_owner_contract.json is a future M9 eligibility table, not an executed generic backend checker. It requires each call's five setup-memory instructions and nonempty target, with only the exact op19 VSLIDEUP.VI offset2/VL<=2 exception; nonempty op24 remains required. Spike raw has no CVX/arch/uop events. This review therefore does not claim DUT token pairing or backend-owner acceptance. Those remain mandatory at any future VCS entry.

Machine-readable admission is REFERENCE_ENTRY_REVIEW.json. This review only reads/hash-checks existing evidence and writes these owned review files; no Host, compiler, Spike, VCS or raw semantic parse was executed.
