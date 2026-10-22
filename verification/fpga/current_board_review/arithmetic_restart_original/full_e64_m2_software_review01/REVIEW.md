# e64/m2 Software Artifact Review

Verdict: NO_BLOCKER_SOFTWARE_ARTIFACT_REVIEW_BUDGET_HOLD. The existing software artifact and Host evidence have no identified equivalence blocker. Reference and DUT admission remain HOLD; neither was executed by this reviewer. This is not RVV execution acceptance or Linux closure.

## Budget Finding

Producer compiled CFG accounting reports mandatory core 2,888,970 and successful-path conservative upper 3,074,202 instructions, including BSS and runtime allowance. The upper exceeds the unchanged 3,000,000 target by 74,202. Actual firmware instruction count is unknown. An upper above target does not establish measured execution above target; it does not justify admission either. No timeout increase, reference run, or automatic optimization follows from this review.

## Exact Scope And Equivalence

- Reviewed `../full_e64_m2_block_software01/`: `source.diff`, `case.c`, `packed.h`, `mask_clear.h`, Host implementation/receipts, proof, compiled inspection and actual disassembly. The previously checked 202 software pins matched; 31 Host log hashes and numeric outcomes matched their receipts. No Host/compiler/reference rerun or raw CSV parse was performed.
- Original provenance is binary-equivalent reconstructed C, not recovered original C bytes. Source retains 35 operations, three seeds, 5,985 calls (4,095 integer and 1,890 FP), 191,520 result elements and 11,970 guards. Original RNG, every-call FP input loop, helper order, vstart check and diagnostic fallback are retained. The dictionary fast path changes scalar validation implementation, not original C byte identity.
- Original input constants are bound to original ELF VA `0x11520` through its actual address-use chain. Five copies of the same input string are not a uniqueness proof. The separate 640-word/5,120-byte FP expected table uniquely matches original VA `0x11560`; linked table bits retain SHA256 `ced4ecb4b7d1cfd206365c91712c955a4f4be5e8d6c73f54b7452c0e1491daa5`.
- SoC disassembly `0x80000adc..0x80000b26` establishes a 32-iteration FP refresh: input indices advance by 1 and 3 modulo 8, then `sd a4,-8(a3)` at `0x80000b16` precedes `sd a5,0(a0)` at `0x80000b1a`. The end address is `a+0x100`. The op>24 gate and subsequent trial branches return through this refresh. Thus all 1,890 FP calls retain 64 stores, including equal-value stores; next-seed RNG is not replaced with cached FP state.
- CAP32, SEW64, physical group2 and 256-byte operands remain distinct from earlier e64/m1. Output is 272 bytes: 34 SD initialization and 34 LD comparison, offsets 0..264. The fifth dictionary block accesses only offsets 256 and 264, not its padded 48 bytes. Both guards are 64-bit `0x5b`, not repeated typed16 `005b`. Legal memcpy accesses avoid uint8-to-uint64 alias casts.
- Both compiled artifacts independently establish mask clearing at exactly 16 eight-byte offsets 0..120. The empty memory barriers emit no hardware fences, calls or branches in that region. Physical mask is 128 bytes, with actual mask load four bytes; upper 124 bytes remain initialized. This is actual artifact evidence, not merely inheritance from e32.
- Compiled proof binds 458 original static helper instructions, no extra RVV validation, unique FP table, dictionary and all call indices. SoC/reference-artifact stack gaps are 869,088/860,696 bytes; main frame is 288 bytes. The original source supplies no explicit fflags oracle; none is claimed here.

## Host Evidence And Limits

Actual software process wait: rc0, 27.623255940619856 seconds, no timeout. Host has 31 invocations: original and packed each positive, eleven result/state mutations and one UBSan trap, plus five missing-state negatives. Twelve non-UB paired transcripts are identical. Positives return 0, result mutations 1, UB trap -4 and missing-state mutations 90.

Coverage includes active/prestart/masked/tail results, both guards/high bits, vstart, signed-zero/NaN/FP result bits, final result, shift boundary and signed division corners. Deleted equal-value FP a/b writes reject at ordinal 1367; fresh output, next-seed RNG and upper mask clearing omissions reject. Dirty masks, unaligned memcpy boundaries and protected-page boundaries are exercised. Host mock helpers prove scalar/model equivalence and instrumentation obligations, not actual RVV execution. Host store counts alone do not prove order; the retained source and compiled FP loop provide that separate evidence.

## Bound Evidence

Full hashes are recorded in `REVIEW.json`. New `compiled_review.json` and its execution receipt are bound separately; they were not retroactively inserted into the sealed 202-pin software manifest. `compiled_inspection_execution.json` records producer inspection exit0, not a reviewer test execution.

Next permitted action is only Zeno's separate static FP-period/unroll proposal. It must preserve each call's ordered a[0],b[0],...,a[31],b[31] writes, original bits/RNG/history, full output and failure behavior. Its cost and actual lowering are not accepted by this report. Compilation or reference of that successor requires the applicable further authorization; existing software remains sealed.
