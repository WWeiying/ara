# e32/m2 Packed Integration Source Gate

2026-10-14: INTEGRATED_SOURCE_NO_BLOCKER for the parent's already authorized single Host/compile stage only. No actual Host, compiled-artifact, cost, reference or DUT acceptance is asserted.

Exact input: `../full_e32_m2_block_prepare01/software01/SOURCE_FREEZE.json`, SHA256 `74a6481ac8cd9e62f4bea87f91973d4cdc2d5d1f7632f11ba96e2f54a4efe800`. All 32 frozen pins independently rehashed and matched. The reviewed scalar header remains byte-identical to candidate SHA `12dea4d7c5b857ca58a6305fc3a3032b9c000c1c62f8e186ad43fd7bf6e4d5b5`.

## Source And Layout

- `case.c` retains original seed/op/VL/mask/start ordering, CAP64 qualification, every-call FP refresh and original helper calls. Source-level 128 ordered FP writes and original mask clear/selected-update requirements carry over from REVIEW.md.
- The fallback block from `unsigned packed=0` through the original result/guard checks is byte-identical to the adapted original C. Returned-vstart checking remains outside the packed fast path. Only successful full-output comparison bypasses scalar recomputation, adding the same CAP to the element count.
- Independently checked the packed source has exactly 33 eight-byte fill spans and comparisons at offsets 0,8,...,256. Typed fill is `0x0000005b0000005b`. The final word includes element63 plus rear guard; there is no short tail read, omitted last element or access to the fifth block's 56 ROM-padding bytes from output.
- Independently reconciled all 5985 persisted row word lists with the generated five-ID dictionary: 1499 blocks, 155786 bytes including IDs, exact first 33 words and seven zero padding words per reconstructed row. Both uint32 guards equal 91. This checks representation consistency, not an independent execution of the scalar model or helper.
- Model source uses the original 640 FP bit patterns and 64-step RNG per seed, preserves every FP call input rewrite, source-capacity gather/slide bounds, reduction/compress semantics and all 1890 FP calls. b[3]=32 is valid for CAP64. No host-float replacement or fflags oracle is introduced.

## Planned Host/Compile Entry

Reviewed `prepare.py`, `execute.py` entry contract through the frozen plan, and `host.c`/instrumentation design. Original and packed variants cover the full sequence and compare complete fallback transcripts for positive plus eleven oracle mutations. The six additional event mutations target equal-old FP writes, FP pair order, omitted upper mask clear, omitted selected bit and selected-bit order. Guard-page, unaligned and every-byte checks cover the exact 264-byte footprint. These are planned tests, not yet observed PASS receipts.

Host hooks observe C assignments; they cannot establish emitted SW/SD/SB widths. Their counters check all 128 FP assignment events per FP call and original cumulative mask order/value, including a clear-before-bitset boundary. Source expected bits are checked using original C semantics and original FP table against the generated words.

The compiler entry preserves the original assembly, checks all 458 helper instructions, rejects extra RVV, requires aligned mask/output and at least 64KiB stack gap, and persists numeric outcomes before postchecks. These remain future artifact obligations. The separate actual CFG review must establish ordered 128 SW, 16 complete SD clears before selected SB paths, full 33-word fill/read, actual memory/frame fit and a complete <=3M positive-path bound. No source cost estimate substitutes for those gates.

## Limits

No Host suite, compiler, Spike, DUT, model generator or raw trace was run by this reviewer. Only pinned files, source, JSON and generated representation were inspected. One local static inspection command initially had a Python syntax typo and performed no audit; the corrected read-only command completed exit 0 (`2362e4`). No producer or sealed file was modified. This source gate does not authorize reference or simulation.
