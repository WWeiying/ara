# Resident QK FS-off: timing reference versus signoff

**Finding:** the timing reference used the pre-fix CVA6 commit stage. It asserts
`dirty_fp_state_o` for an ACCEL/VFP entry that takes an illegal-instruction
exception without retiring. FS was successfully cleared; the QK program and
its strict expected values are correct. This is not a failure first introduced
by the ex-fp-credit candidate: the failing command ran the parent reference.

## Firmware evidence

The [reference command](../../out/ex-fp-credit-20261122-02/soc/reference/resident_qk/run.command.json)
used the payload-credit simulator. Its QK ELF and the stage3 gold ELF both hash
to `d7823dca2c700174223629df36a7dc65de1828ee313e7219d57a059c0b5bc7fa`.
Comparing the [reference log](../../out/ex-fp-credit-20261122-02/soc/reference/resident_qk/run.log)
with the [gold log](../../../../ara_dsa_signoff_integration/verification/out/stage3_qk_boundary_v2_20261110_01/work/run.vcs.log):
all 35 CASE keys match, all DATA rows match, and only case 11 phase 0 differs.
Both report one illegal exception (cause 2) at PC `0x80000230`.

| Observation | Gold | Timing reference |
| --- | --- | --- |
| before_mstatus | 8000000a00000680 | 8000000a00000680 |
| trap_mstatus | 8000000a00001e00 | 8000000a00007e00 |
| after_mstatus (before software restore) | 8000000a00000680 | 8000000a00006680 |
| trap_csrs_valid | 0 | 1 |
| recorded mtval | 0 (not sampled) | 0605705b |

ELF disassembly: `0x80000210` clears mask `0x6000`; `0x80000224` reads it back.
The handler samples mstatus at `0x80000420`, before any FP CSR access. Only when
both FS and VS are nonzero does it read mtval, fcsr and vstart and set the valid
flag. The resume path reads mstatus at `0x80000254`, before restoring it at
`0x80000268`. The [checker](../../performance/resident_rvv/qk_shared/qk_boundary/main.c)
counts two independent errors: unexpected valid flag and nonzero FS in the
three-sample mask. No separate mtval or fflags defect is required.

## Independent VCS replay

Used the [original frozen runner](../../../../ara_dsa_signoff_integration/verification/out/resident_pv_commit_dirty_20261110_03/inputs/test/run.py)
unchanged: fresh prepare, compile and simulation under a direct signoff service.
The [replay receipt](../../../../ara_dsa_signoff_integration/verification/out/resident_fs_csr_20261123_01/report.json)
reports PASS with both source and image pins intact. Testbench SHA-256:
`9d8f1a42b02934b9900925867084147c165f4b1a7b898e18f395e382b58ea101`.
The two DUTs are complete commit stages (PRE module renamed for co-instantiation).
The installed patch's commit-stage hunk has the same PRE/POST Git blobs
(`b259f99e` / `a91ee67f`) as those sources. SHA-256 identities:

- PRE: `bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60` (timing reference filelist source).
- POST: `ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249` (stage3 gold source and fixed DUT). The live dep also read POST at final inspection; the existing reference image does not inherit a later workspace change.

The reference first-pass decoder gives resident QK and PV the same commit
classification: ACCEL, load, VFP=1. With VS on and FS off it still marks the
instruction illegal. PRE ORs the ACCEL/VFP term outside the ACK gate; the CSR
file sets `mstatus_d.fs=Dirty` on that input. POST gates this term with ACK,
not dropped, and no entry exception. [VCS rows](../../../../ara_dsa_signoff_integration/verification/out/resident_fs_csr_20261123_01/work/simulation.log)
for WT and WB:

| Original test case | ACK | Dirty PRE / POST | fflags write |
| --- | --- | --- | --- |
| illegal_fs_off | 00 | 1 / 0 | 0 |
| exception_drop_ack_not_retire | 01 | 1 / 0 | 0 |
| pv_retire | 01 | 1 / 1 | 0 |

All 72 case rows and the completion marker match the original signoff replay.
Old dirty mismatches: 11 WT + 12 WB. POST: 0. All non-dirty outputs matched
in 72/72 checks. This proves the component mechanism, not the first offending
cycle in the untraced QK run or a new SoC timing acceptance.

**Recommendation:** require the registered POST digest in the resolved compile
inputs for both reference and candidate before building new images. Rerun the
strict QK boundary on both with the identical ELF; keep the old reference FAIL
and gold intact. Do not mask FS, suppress CSR checks, or count this component
PASS as a replacement for that gate.
