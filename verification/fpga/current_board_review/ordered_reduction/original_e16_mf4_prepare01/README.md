# Original e16/mf4 Ordered Reduction Single

**REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW.** Software and one
bounded Spike reference only. No VCS, RTL build, live-job query, source-loop
shortening, reference retry or Linux replay. This is one authentic archived
reduced case, not the full6720-call parent, all11 originals, or current DUT
acceptance. Stop here for independent source/reference review.

## Source And Oracle

Canonical source is handoff03/rvv_small_redspecial02/
rvv_small_fp_redspecial_e16_mf4. `sourceproof.json` binds its case/manifest,
original and reduced Linux ELFs, all six source/header files, GNU tools,
integration wrapper/runtime and both new software ELFs. Corresponding01/02
source files and reduced ELF are byte-identical. `source_supplement.json`
also compares all6720 fixture pairs against the archived JSON and the original
full Linux ELF against its campaign copy. The old01 default-QEMU FP16 illegal
instruction is an environment failure, not evidence of an RTL failure.

Only Linux entry/output/exit are adapted using the unchanged integration
adapter. Original scenario/input/64-word seed/64-byte mask generation and
all surrounding nested loops remain intact. There are3360 fixture selections,
6720 sticky candidates, **one actual op0 call**, and no earlier vector helper
calls hidden behind the3090 skipped candidate coordinates.

Selected tuple: scenario3/l4/mode3/frm0/op0/sticky0, VLEN1024, e16/mf4,
cap16/VL8. Fixture **bank1 row1545** is canonical NaN0x7e00/NV16;
bank0 at the same row is +Inf0x7c00/flags0 and must not be substituted.
Input alternates +Inf/-Inf; seed words all +Inf; mask bytes0x24 select
elements2 and5 within VL8. All144 output bytes are checked: two result bytes,
126 preserved destination-tail bytes and16 outer guard bytes, sentinel0x5b.

All21 instruction encodings of op0, and the unused op1/op2 helpers, were
compared against the stripped original Linux ELF and both new software ELFs.
No helper instruction, original fixture or output oracle was removed.

## Measured Reference

The initial1M authorization was **NOT_RUN_STATIC_BOUND_INSUFFICIENT**.
`BOUND_ANALYSIS.md` establishes mask cost1,612,800, certain total lower
bound1,801,190 and conservative whole-program envelope2,070,768.
Independent cost review uses the looser2.2M envelope. The user explicitly
approved the new3M/256MiB/120-second reference before its unique execution.

`reference03M/execution.json`, `audit.json`, `ledger.json`, and retained full
`commits.log` establish:

- Worker elapsed4.3752 seconds including post-run input pin checks, rc0;
  raw120,844,625 bytes. All input pins unchanged.
- Firmware to successful HTIF store: **1,858,335** instructions; raw total
  **1,860,000**, including five boot-ROM instructions and1660 original
  side-effect-free post-HTIF park instructions.
- Target exactly once at Spike PC0x80000764, raw ordinal863262.
- Full input16, seed64, mask64 and old output144 at helper entry; all21
  helper retirements and full vector load/store address footprints.
- Actual result0x7e00, NV16, returned vstart0, packed status0x1000000000;
  original frm/fflags saved and restored to0.
- All144 original LBU output checks in order, complete original PASS summary,
  wrapper PASS, and actual HTIF store value1. No diagnostic failure marker.
- Actual mask/seed retired counts match static1,612,800/122,368 exactly;
  all6720 bank1 fixture-field reads and the complete original loops remain.

`reference03M/CONFIG_DELTA.md` and `.json` explicitly record actual ISA
**rv64gcv_zfh_zvfh_zvl1024b** versus the later parent file's
**rv64gcv_zvfh_zvl1024b**. This is **not exact-profile contract PASS**.
Both ELF/resource identities agree. Offline classification of the full raw
finds zero scalar FP instructions of any width and one original vector FP
reduction. The user permits executor-PASS handoff with this disclosed delta;
independent review must assess its effect on this concrete positive test.

## Host And Handoff

`host.json`:13 checks passed, comprising one positive plus12 original-C
oracle negatives (missing/extra flags, wrong NaN, nonzero vstart, guards,
first/last store tail, wrong-width result, wrong-bank result, missing write).
The Host mock independently requires original input/seed/mask/full old output.

`reference03M/checker_host.json`:15 checks passed, one actual extracted
witness plus14 offline mutations (NV/result/vstart/guard/tail/bank/type,
seed/mask, CSR restore, short store, missing HTIF/read/encoding). These are
Host-only checker tests, not additional Spike executions or independent review.

`READY.json` pins the final source, executable ELFs, original evidence,
commands, approval/config delta, full raw, audits and Host results. The SoC
ELF is prepared for possible later M6 admission; none is granted here.

Key SHA256:

```text
SoC ELF eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162
Spike ELF afa05463645a429d2467b226fda805f7c8a655189743339555d99adb2b6be1ba
sourceproof f6efe2b2b360e96d4caa69fef05764bf205040f6c7347033e01cbd19562185af
raw 4f0723a9a59985cf5d25177ee9b0ba74c7dc23eccf1001294d7f4f8a4b312bf5
audit 1c997f982d205cddc1f1eb24c203f6cce505275fd6ac9ce3563d280176e60da0
```
