# e32/m2 Actual Host And Compiled Artifact Review

2026-10-14: NO_BLOCKER in the completed Host/identity/layout/write-profile checks below. Complete positive-path CFG cost remains pending; this is NOT COST_PASS or reference/DUT admission.

Input directory: `../full_e32_m2_block_prepare01/software01/`.

| Evidence | SHA256 |
| --- | --- |
| SOURCE_FREEZE.json | `74a6481ac8cd9e62f4bea87f91973d4cdc2d5d1f7632f11ba96e2f54a4efe800` |
| proof.json | `fa449f1e0316dadfa65a8c4d1fb649960a56d57a52740656d24b2cd5c2284614` |
| pins.json | `7202a25ac7244210fef319ae1b0f401863c76ffa94fc96b10b4bd27bdc3f0b8b` |
| soc/program.elf | `b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6` |
| spike/program.elf | `cbe657411501c8cf974d3c6830caea39847563cfa5f6451ef335eca6e5e809e7` |

## Actual Receipts And Identity

Actual outer Host/compile returncode is integer 0, no timeout, elapsed 50.260012093000114 seconds. Independently matched all 30 per-run outcome records to their persisted numeric receipts and log hashes: original/packed each one success and eleven expected oracle failures; six fresh-write/order mutations each exit 90. All twelve original-versus-packed complete output transcripts are byte-identical. Negative returncodes remain negative-test evidence, not relabeled successful child exits.

All 222 manifest pins were independently rehashed and match. Both ELF hashes match proof. Each backend's 458 helper instructions matches the actual generated disassembly and original archived instruction sequences; independent opcode scan found no extra RVV. Original archived/reconstructed ELF identity is `978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c`.

## Actual Machine Instructions

- Both backends contain exactly 128 LW / 128 SW in the expanded FP refresh block. Independently checked each alternating load/store: source cache offset `192+4*(i%8)` for a[i], `192+4*((3*i)%8)` for b[i], then destination offset `4*i` through 252, a before b. No merged SD or omitted equal-value store. SoC block is 0x80000e96 through final SW 0x80001192; Spike is 0x80000e92 through 0x8000118e. Each block then jumps to output initialization.
- Spike dispatch at 0x8000095a reads the current op, compares against 24 and branches to FP refresh for op>=25 before output fill/helper call. This matches the preserved per-trial source placement, including VL0; no source freshness is inferred merely from final values.
- Independently followed compiled mask branches and jumps for modes 0/1/2. Each yields the original ascending selected-index sequence with 64/32/9 SB respectively. The shared mode1 tail at Spike 0x80000932 was included, not mistaken for missing updates. The mask region contains all sixteen zero SD addresses, mask+0 through mask+120, before mode dispatch. Counts across source groups remain 35280 clear SD and 77175 selected SB.
- Both arithmetic_main functions contain exactly 33 output SD and 33 output LD at offsets 0,8,...,256. The last full 8B transfer therefore includes element63 and rear guard. No output read of dictionary padding is present. An initial broad textual read scan also saw unrelated Spike runtime s0 loads; restricting the scan to arithmetic_main confirmed the intended exact 33, without changing any artifact or expectation.
- Both source/private backend maps preserve full backing and large stack separation: SoC 867624 bytes and Spike 859232 bytes between bss end and stack top. arithmetic_main has a 336-byte frame. Complete nested-frame and CFG runtime accounting remain part of the pending cost report, not an implication of this gap alone.

## Scope And Pending Gate

Full original source-port scope remains 5985 calls / 35 ops / CAP64, 383040 results, 11970 uint32 guards, 197505 whole-word output reads, 77805 helper instructions and 1890 FP calls with 241920 source SW. Original data/guard/vstart oracle and fallback remain; no fflags oracle is claimed.

This review read only existing files, persisted receipts and disassembly, plus independent static parsing/hashing. It did not rerun Host, compile, Spike, DUT or any raw trace. No sealed files or RTL were changed. The earlier illustrative 2.55M estimate is not used as a measured/derived cost acceptance: await complete actual CFG accounting <=3M before considering a separately authorized reference entry.
