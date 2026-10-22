# Two Original FOF Singles: Software and Reference Ready

Status: **own Host/reference executor PASS; pending Main/independent review;
NOT DUT acceptance**. Exactly two source singles and two Spike invocations total.
No RTL edit/build, VCS, Linux execution, or existing live-task query occurred.

## Authentic Scope

Sources are the archived `rvv_small_exceptions01` singles under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/`:

| Case | Historical failed ELF SHA-256 | SoC ELF SHA-256 |
| --- | --- | --- |
| e8/scenario0 | 24f4844318a01f821681aa568aee42c1560b0f1705218dca0efa44eed34c9cbe | 40cfaa6efb389fba0d5a55d8e7d58d67b7c927b0ff499ae3e5d0d77337a4a674 |
| e64/scenario5 | a688dbfe9f1887fa028764d2e7decbdcfb3fd55460aa1e572b89f88b1c85a316 | 9e9e8da2ace6b0965f1c5989e4ac03ddcb4b16bed54d61ac795ad5cf4a213ecd |

`software01/e{8,64}/source_proof.json` binds original C/S/ELF, manifest and
measured failure context. Both reduced C files differ from the hash-verified
detail-parent C only in their original one-round/one-scenario loop selection.
Original assembly is unchanged; all11 instructions of each load helper and
all3 capacity instructions match the actual archived ELF machine code. The
unused ordinary helper is preserved and forbidden from execution by the observer.
No guessed predecessor, retry, or synthetic warmup is added.

The adapter preserves 130 physical output elements,16 physical mask bytes,
four initialized source words, actual capacity128/e8 and16/e64, the complete
original11-instruction FOF helper, VL8 store and original result/guard oracle.
The helper consumes one logical mask byte atVL8; this does not reduce the
16-byte physical source allocation or its initialization/checks.

**e8:** baseP-4, maskff, source11/48/85/122; immediate returned packed value
records VL4/vstart0. Final out[1..4] is strict; **out[5..8] is unconstrained**
in the C oracle and every final byte-map check. Different values there pass Host.
Original out[0]/out[9] guards remain0x5b. The helper restoresVL8 before its store,
so the later completion CSR correctly reportsVL8, notVL4.

**e64:** baseP, mask0, no active elements. Old-vd is uint64_t value0x5b,
not memset(0x5b); all8 results and original guards0/9 are strict. Returned
VL8/vstart0 and later VL8/vtype24 are checked. All130 output elements remain0x5b.

Both enter real S-mode with Sv39 and an inaccessible second-page leaf. The
first page remains readable. This preserves the protected-address effect,
not Linux PROT_NONE PTE encoding or clone/wait/signal semantics. Neither target
causes an architectural trap; only the completion S-ECALL is allowed. No remap,
target retry or repair path is present. Full8KiB backing data,12KiB page tables,
outer guards, original extra output storage, fcsr/vcsr and CSR save/restore
checks are explicitly supplementary to the original Linux oracle.

## Measured Reference Results

Each final ELF ran once with actual profile `rv64gcv_zfh_zvfh_zvl1024b`,
`--priv=msu --pmpregions=0 -m2`, instruction cap1,500,000, wall120s,
RLIMIT_FSIZE256MiB. `execution.json` persisted actual numeric wait status
before any observer check. No limit increase, changed ELF or reference retry.

| Case | Actual rc | Spike seconds | Raw bytes | Firmware records | Scalar checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| e8/scenario0 | 0 | 2.974493 | 20376118 | 169885 | 5477 |
| e64/scenario5 | 0 | 3.024279 | 20918270 | 172547 | 5481 |

Commit-format totals are169890/172552, including five boot records each.
Firmware totals conservatively include3933/2140 original post-HTIF park records;
nonparking firmware counts are165952/170407. The observer only permits that
original park PC after HTIF1; all required helper/oracle/CSR checks precede exit.

Accepted result paths:

- `recovery01/audit_e8_01/status.json`, SHA
  `a42b0225e7cd2ce788d821060b84a4b46cd47ea08f70fecb0a66b181390726c9`.
- `recovery01/reference_e64_01/status.json`, SHA
  `ee4da22ab24d1abba8ef62b400043284bdb26b894350e7eb7ff797dc1b3e105c`.

e8 actual target PC0x80000954 (Spike; SoC0x8000094c) reads exactly
0x40000ffc..0x40000fff and shortensVL to4. e64 target PC0x800008fc (Spike;
SoC0x800008f4) has no data-memory reads and retainsVL8. Both execute the original
helper once and preserve the complete original VL8 output store. Raw vector
commit text, all memory stores, actual S-ECALL CSR records and before/after
byte-map checkpoints are retained. Spike no-read evidence is **not** proof of
future DUT no-MMU/no-AR behavior; that requires target-VID-scoped DUT evidence.

## Preserved Checker Correction

`reference_e8_01/not_completed.json` stays NOT_ACCEPTED. The first observer
mistook startup's BSS `fx_completed=0` for final DONE. The unique e8 Spike
process itself exited0 and was not repeated. `recovery01/RECOVERY.md` binds
the measured first rejected write (PC0x80000046, sd-zero, width8).
The successor only narrows boot-versus-final completion classification;
no numeric oracle or allowed FOF region changed. Same raw was checked offline.
e64 then used the same corrected observer for its first and only reference.

`recovery01/startup_prefix.json` separately verifies full ordered BSS clearing
and exactly one completion initialization in each actual prefix, stopping at
main (33276/34180 lines). This proves the two captured startups, not a claim
that the runtime observer alone counts/rejects every possible duplicated boot
write. It performs no second full-reference parse. Both original and corrected
checker identities, old rejection and all process outcomes are preserved/pinned.
`EXECUTOR_WAITS.json` records completed command-session exit values explicitly.

## Host and Future Budget

Both compiled Host models match2836 independent Python rows each. Host boundary
checks include all four initial/final byte maps, two distinct allowed e8
undefined-region patterns, and31 rejected corruptions/missing-byte cases across
both SEWs: results, guards, unused storage, physical mask, source, page tables,
VL/vstart/context and e64 repeated-byte initialization. Five additional Host
negatives reject incorrect completion phase/PC/value/width/BSS boundary.

The pre-run compiled successful-path upper bounds were1000296/e8 and892390/e64,
not inferred after trial. Actual reference cost is much lower. At slow273
retired/s plus20%, the conservative measured-record proxies are746.75/758.45s
per case. Comparable H/M6 single rates suggest several minutes, but no fixed
VCS performance promise follows from Spike. A future reviewed per-case budget
of1800..3600s would remain below3h; no budget or DUT launch is authorized here.

Main review comes next. These are two source-derived single preparations,
not closure of all8 historical ELF records or the96-call Linux parent programs.
