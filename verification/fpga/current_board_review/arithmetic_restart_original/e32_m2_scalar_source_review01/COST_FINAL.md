# e32/m2 Compiled Software Gate

2026-10-14: NO_BLOCKER. Actual Host/compiled-artifact checks and static positive-path <=3M cost gate accepted. This is a software gate only: no Spike/reference or DUT execution has occurred or is authorized by this report.

This completes `INTEGRATED_SOURCE.md` and `ARTIFACT_STAGE.md`; those records remain unchanged. Full original 5985-call, 35-op, CAP64 source-port scope is retained, not a prefix or original Linux closure.

## Exact Evidence

| Artifact | SHA256 |
| --- | --- |
| `full_e32_m2_block_prepare01/compiled_audit01/RESULT.json` | `69534a528c93f51ec0b6dae984080b6d1792d6726e144ac8f15a5bb2e4c656c4` |
| `compiled_audit01/inspect.py` | `800e9107ffe163723e53808fe9c1f798d96ae1f4272ab8791872bae09d631b47` |
| `software01/proof.json` | `fa449f1e0316dadfa65a8c4d1fb649960a56d57a52740656d24b2cd5c2284614` |
| `software01/pins.json` | `7202a25ac7244210fef319ae1b0f401863c76ffa94fc96b10b4bd27bdc3f0b8b` |
| `software01/soc/program.elf` | `b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6` |
| `software01/spike/program.elf` | `cbe657411501c8cf974d3c6830caea39847563cfa5f6451ef335eca6e5e809e7` |

The review independently verified the cost-result evidence hashes and arithmetic without executing its report-generating inspect.py. Previous independent checks rehashed all 222 software pins, matched actual outer returncode 0 / 50.260012093000114 seconds, all 30 expected Host outcomes and twelve original/packed full-history transcript pairs.

## Compiled Semantics

Both actual ELFs preserve 458 original helper instructions and contain no extra RVV. Both have exact ordered 128 SW per FP call, with the corresponding eight-slot cache load permutation, no source SD merge, and all trial reentries reaching the op>24 refresh gate. Exact full mask initialization precedes the original cumulative selected SB events, including the compiled mode1 shared tail. Totals remain 241920 FP SW, 35280 mask-clear SD and 77175 mask SB.

All 33 output SD and LD offsets are 0..256 in steps of eight. The last word contains element63 plus rear guard, not padding. Independently checked each linked ELF contains exactly one matching generated dictionary, ID array and the original 2560-byte FP golden table. Original oracle fallback, all 383040 results, 11970 guards and 5985 returned-vstart checks remain. No new fflags oracle is claimed.

Main frame is 336 bytes. The static sum of function frame allocations is 536 bytes for SoC and 584 bytes for Spike, well below the retained 64KiB reservation; actual bss-to-stack gaps are 867624 and 859232 bytes. This static sum is used with the inspected nonrecursive successful call graph, not as a generic proof for recursive execution.

## Actual CFG Cost

The audit weights actual linked Spike instruction regions, not the earlier illustrative source estimate. Independently checked term arithmetic, instruction-PC membership, source visit multiplicities and control boundaries. Masks occur in 735 groups per mode, FP refresh in 1890 calls, and the complete helper/output oracle in 5985 calls.

| Component | Instructions |
| --- | ---: |
| Three mask paths, including clears and dispatch | 366030 |
| FP refresh, 257 instructions per call | 485730 |
| Trial gate, 33 SD, helper dispatch and first comparison | 395010 |
| Remaining 32 LD comparisons and counters | 855855 |
| Original 13-instruction helpers | 77805 |
| Mandatory core subtotal | 2180430 |
| Control/RNG/cache/prologue union terms | 131560 |
| BSS initialization bound | 10345 |
| Successful startup/printing/exit allowance | 20000 |
| Positive-path static upper | 2342335 |

Headroom to the requested 3000000 gate is 657665 instructions. Union terms intentionally overcount mutually exclusive control branches; their counts must not be called measured retirements. The source/actual disassembly confirms the repeated positive loops and transitions used by these terms.

The 20000 allowance is comfortably sufficient for the inspected successful runtime remainder, including the small non-BSS bootstrap/capacity/main/exit work: fewer than 256 output characters, at most six decimal conversions of at most 20 digits, bounded string scans, and the actual finite replay_write byte-copy loop. It is not an allowance for unexpected traps, mismatches, arbitrary output or unbounded parking. The terminal self-loop at 0x8000007e is outside firmware-through-success cost. Error fallback execution remains intact but is not included in the positive-path bound.

## Limits

This is a STATIC cost bound on the compiled reference backend, not actual Spike retired instructions, DUT wall time or a <=3h performance guarantee. Future reference entry must independently bind these exact ELFs, real startup/exit contracts and full oracle before any separately authorized execution. No reference, Host rerun, compilation rerun, VCS, raw trace or live process was executed/read by this reviewer; only existing metadata, source, binaries and disassembly were inspected. No sealed input or RTL was modified.
