# Software02 Independent Artifact Review

Verdict: NO_BLOCKER_SOFTWARE_ARTIFACT_STATIC_COST. Reference and DUT have not run; this is not source-history execution acceptance or Linux closure. No new execution is authorized by this report.

## Identity And Actual Receipts

Freshly verified all 489 artifact pins and all 25 READY pins, zero mismatches. READY SHA256: `408897aee9a25e6d50ebbab2b3e8fa318b6d6c1fc87e9f4993b8bc493720556c`. Artifact RESULT: `301e510e370c4c029f21195bd8b07593e020ecd82a93771346185011fea58a0a`. PINS: `d2c1fa063d0cd4135a5783bef6d9b1c932f22160766e5ce458bff0c4909a2ee2`.

Preparation actual numeric exit0 /35.356501386s; linked audit exit0 /63.385392338s, neither timed out. New Host46 logs each match their digest and expected numeric exit; short Host exit0 /0.005690717s. The Host C expansion differs by parentheses: old Host46 is NOT inherited. The new full46 and six short cases supply fresh evidence. Host C is explicitly not RV64 ASM execution.

Compared actual source copies: case.c, fp_period.h, gold_data.S, mask_constant.h and host.c are byte-identical to software01; packed_cache.h is exactly the approved static_sticky01 header. Both actual compiler command receipts match the old fixed command after output-directory substitution, plus only SPIKE_REFERENCE=1 for the Spike backend. No flag search. Old software01 HOLD and failed receipts remain unchanged.

## Linked Proof Reviewed

Read audit.py, leaf_cfg.py, main_cfg.py, actual function records and closed result receipts; did not rerun their analysis. Auditor binds every decoded instruction to executable ELF bytes, original 458-helper/1688-byte hash and source-order windows, and symbol-qualified dictionary/IDs/FP payload. No additional RVV. Actual _start GP AUIPC/ADDI gives SoC 0x80041a5a and Spike 0x80041b08; only those two startup instructions write GP. Startup BSS initialization is explicit, not unknown-register defaulting.

All 65 comparator sites are BEQ displacement6 followed by C.LI a0,1. Compare operands differ from a0. Equality preserves bad0 or bad1; inequality sets1. The scalar walk propagates exact ID/cache values through hit/miss paths, and its seven linked negative paths retain all65 actual reads after errors, including upper/lower-half and tail corruption. No branch can skip later actual reads based on sticky state. Independent inspection of the actual linked scalar leaves found no callee-saved register destinations and no stack transfers/adjustments: old six save/restore pairs are genuinely absent, not pre-credited.

Scope remains 5985 calls, 35 operations, SEW32/CAP128, 766080 results and 11970 guards. Closed artifact proof records 389025 actual LD (65/call), 124041 expected LD, 53865 ID LHU, 33123 cache hits and 14757 misses; first fill each call and full miss refresh are checked. Final offset512 reads exactly element127 plus rear u32 guard. FP has 483840 ordered SW with eight fresh input LW per FP call; masks have 35280 clear SD plus 154350 ordered cumulative SB. Output initialization has 389025 SD. No fflags oracle is claimed.

## Whole Positive Cost

The new actual scalar main walk independently checks all indirect target addresses, seven arguments, original ordering, 2205 mask groups, 1890 FP refreshes and seed RNG assignments. Unknown caller-saved values are discarded at summarized calls rather than set to zero. Summaries explicitly assume successful vector results, returned vstart0 and capacity128; this is a conditional cost calculation, not a vector reference execution.

| Component | SoC | Spike |
| --- | ---: | ---: |
| Capacity + original helpers | 77808 | 77808 |
| Mask | 235935 | 231525 |
| Output initialization | 424935 | 424935 |
| Cache/comparison | 1123125 | 1123125 |
| FP setup | 529830 | 529830 |
| Main including callers | 372492 | 360520 |
| Runtime writes + formatter | 4775 | 7155 |
| Startup | 35926 | 59501 |
| Main trampoline + exit | 6 | 8 |
| Whole positive upper | 2804832 | 2814407 |

Reviewed actual number/replay_write/_start/replay_exit listings: bounded decimal conversion and string-length loops, fixed-length output loops, and BSS clear loop support the conservative static-PC weights. Exit includes the completion write and one park instruction, not indefinite parking. Main stack traffic is counted; actual stack gaps are 769192/760800 bytes. Margins to3M are 195168/185593. These are independently assembled whole-program terms, not old mandatory-core subtraction. They are neither measured retired counts nor a VCS runtime guarantee. Error fallback cost is outside the explicitly positive-path bound; its source remains unchanged.

SoC ELF: `6adde60cb19b74d8aa1e1c44a2219042d2a482da18e824772ba2cdf47bd940bf`.
Spike ELF: `a91b41df8ad8156243f0e79d998a0ec9783f2bc2113dfe6016404988abb9970f`.

Independent work was read-only JSON/source/listing inspection, byte comparisons and SHA256 checks, with numeric inspection exits0. No Host, compile, reference, DUT or large raw parse was repeated. Parent may decide the next bounded reference stage; current runtime execution remains unvalidated.
