# Original Mask Array Size Correction

This post-prepare corrective note does not change any sealed source, READY,
reference, plan or prior document. Historical wording "original mask128B" is
incorrect for these NF2 e16m1 singles. Correct size: **16 bytes**.

Exact example source:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01/singles/rvv_small_fault_segment_nf2_e16_m1_u0_s0_b1_m2_f0/scenario.c`
SHA `416a36bd5b8465ccf4fc4149e964f50dda6685b8b457fbe1fd57515408162b2c`.

- Line52: `#define LMUL_NUM 1`.
- Line56: `#define CAPACITY_LIMIT (128*LMUL_NUM)`.
- Line65: `static uint8_t mask[CAPACITY_LIMIT/8];`.
- Line249 initializes exactly `CAPACITY_LIMIT/8` bytes.

Thus the source allocation is 128*1/8=16 bytes. The Sv39 fixture also retains
16 mask bytes per case; its cap64 vector mask load consumes eight bytes. Full
output, guards, memory, CSR and exception checks remain unchanged. The original
ELF is stripped: this is a source-formula proof, not a claimed original mask
symbol size. It does not assert byte-identical Linux-to-Sv39 adaptation.

Independent correction: `../nf2_remaining34_reference_audit01/REVIEW.md`, SHA
`e418fcbf76d581738ef08aeec87ca758cf3458238e6836bfc3dc59bb04ea823e`;
per-source verification in `source_audit.json`, SHA
`fd9b7e4d5830e8587014846d8a0df00d650082332ae4860c320a845d1116e4e7`.
The sealed new runner README already states the corrected 16/16/8-byte domains.
