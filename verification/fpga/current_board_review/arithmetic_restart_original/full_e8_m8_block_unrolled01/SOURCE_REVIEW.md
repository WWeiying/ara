# Full E8 M8 Full-Unroll Entry

Software/reference only. No DUT authority; old full_e8_m8_block_prepare01/HOLD.json is preserved.

Only packed.h code-generation change: explicit128 eight-byte initializer copies plus exact2-byte tail;
explicit16 blocks of8 comparisons plus exact2-byte tail. Same compiler/flags; no new vector instructions.
All source case/model/Host/dictionary/seed/order/original.S identities match prior preparation.
Full4095 calls,3 seeds,CAP1024,mask128,4193280 result bytes,8190 guards remain mandatory.
Mismatch fallback remains the original byte-by-byte oracle/error counting.

Host: original and packed positives and7 mutations match; intentional shift64 UBSan negative traps
in both variants (18 actual processes). Exact1026-byte boundary/unaligned memcpy and all-byte mutations
are part of that unchanged Host contract. memcpy avoids aliasing/OOB. No loops/history/oracle omitted.

Corrected static_cost02.json supersedes static_cost.json, which omitted one LD following a bare RET
due to newline-consuming regex. Both retained; no recompile/reference was needed.
Actual net saving446880 predicts2825046 firmware instructions (+10000 reserve=2835046), NOT measurement.
GCC outlined packed_mismatch.constprop.0:451 success instructions +6 caller; no stack memory.
Main frame304B unchanged; allocated image +1984B. Spike stack gap647648B, SoC656104B, both >64KiB.

Compiler scheduling puts the tail SH after100 SDs, before remaining28 SDs.
lifecycle.py binds each of129 actual PC/instruction/width/offset entries in that exact order,
with full per-call freshness and original boot checks. Missing any SD or tail is rejected.
reference_check.py otherwise differs from accepted8-register observer only in its local HERE path.

Focused Host first receipt exit1 is preserved:15 semantic tests passed; one text-only comparison
mistakenly rstrip'ed literal backslash+n, exposing2 extra final newlines. test_text02 fixes ONLY
artifact normalization and additionally asserts AST equality; its actual exit0 is separately recorded.
No semantic observer changes were made to resolve that test.

Reference budget unchanged: one attempt,4M hard debug steps,120s,768MiB raw bound; <=3M firmware
required for READY, otherwise HOLD. Numeric execution and full-raw parser exits persisted separately.
No reference before exact Tesla review binding entry.json. No DUT even after reference PASS.
