# Combined Reference Terminal Review

Verdict: ACCEPTED_REFERENCE_ONLY_NOT_DUT. No blocking issue in the combined sealed reference terminal and focused capacity supplement. Reviewed 2026-10-14 by Hilbert; no test, reference, raw scan, or DUT was executed by this review.

Evidence root: `../full_e16_m8_sentinel_mask_reference_entry01/`.

- Original `reference01/result.json` SHA256 `563c7295b58c6029adf1fda245eec77d7c62d1b92db2d6d2975b6594a59b9d04`; original READY SHA256 `bc6dc1ba90bd6906d16f2c2111380947ce0d92bf3aa3f49c2eabec044f754b87`.
- Spike PID3510386 actual wait0/10.894263s; full audit PID3510544 actual wait0/152.510565s. Neither timed out or retried. These are child receipts, not a claim about an outer service exit.
- Full original 4095 calls, 2096640 results, 8190 guards, 4095 returned-zero vstarts, 13*4095 helper instructions, 528255 output reads. Each typed output is 1028B, with a 4B tail; CAP512/SEW16/m8, physical mask128B. Input backing arrays are 2048B each, not an assertion that the m8 register group exceeds 1024B.
- Actual firmware-to-HTIF 2540955 satisfies the explicit `reference02.py` READY gate <=3000000. Earlier firmware-to-exit 2540949 is not substituted. EOF checked, including 4040 pure-park records. Gold109575 remains static CFG evidence, not an invented dynamic count.
- Supplement READY SHA256 `ba7d608e13b281786e6e643f21326a139701bff0c433a1d8c99e5a872ea025ec`; result SHA256 `1513e3f21563f1b313b518c7478358c0c10669c9f123447b1ed48a743bcbfccc`.
- One native rg child PID3522432 actual wait0/0.569116s extracted 273B, bounded to 65536B/120s. Actual original lines7301..7303 are consecutive and each PC appears once: 8000199e/52fd sets t0=-1; 800019a0/00b2f557 returns a0=512 with VL512/VTYPE11/vstart0; 800019a4/8082 has no recorded side effect. The prior t0=512 suggestion is not used.
- Read the tiny extracted witness and parser, not original raw. Parser checks exact PC/code/order/count/context and rejects added effects. Existing HOST02 13 tests rc0/1.620045s, HOST03 5 tests rc0/0.266707s, and capacity Host 1 positive/19 mutations rc0/0.116593s are separate short checks, not fullstream substitutes. Mutations cover missing/duplicate/reordered records, code/window, t0/a0/VL/VTYPE/vstart and ret effects.
- Raw425581826B SHA256 `0d425b05da1c75bc16818717b0c0ee876010edd8b6822e8d22ae3ae446eef1f6` is inherited from the sole full audit, not rehashed. Current stat matches supplement before/after: device64770/inode37166792888/size425581826/mtime_ns=ctime_ns=1792021275998331423.
- Freshly checked 283 of 284 supplement READY pins: all match. The large Spike executable identity is inherited from sealed execution/pre-post pin evidence, not freshly hashed in this metadata review. No raw file is in that fresh hash pass. Actual source, checker, profiles, ELF, receipts and supplement bindings are covered by the checked pins.

The old capacity qualification HOLD, HOST01 failure and pre-scan wildcard-import failure remain untouched. The latter failed before Popen/raw read; successor performed the sole actual rg scan. This combined decision resolves the capacity qualification gap without claiming the old checker already proved it.

Scope stops at complete software reference acceptance. No new semantic raw parse, no Linux historical-symptom closure, no DUT/backend-token acceptance, no runtime guarantee, and no VCS launch authorization. Discuss runtime budget separately before any DUT admission.
