# e32/m2 Full5985 Software Ready

2026-10-14: Host/actual compilation and independently reviewed static cost gate accepted. No Spike/reference or VCS/DUT was run. This does not authorize either one. The old sealed scalar candidate and HOLD records were not changed.

## Actual Evidence

- Software: `software01/`. Final source freeze SHA `74a6481ac8cd9e62f4bea87f91973d4cdc2d5d1f7632f11ba96e2f54a4efe800`.
- Unique Host/compile child PID3312334, actual returncode0, no timeout,50.260012093s. Durable `software01/execution_command.json`, `execution_pid.json`, `execution_receipt.json` and per-child command/log/exit files.
- 30 Host outcomes as expected: original and packed each run twelve full5985 histories (positive plus eleven oracle mutations), plus six freshness/order negatives. All twelve paired transcripts match exactly. UBSan, unaligned264B, every-byte corruption and protected-page footprint checks included.
- Actual linked-code audit command: `python3 -B verification/fpga/current_board_review/arithmetic_restart_original/full_e32_m2_block_prepare01/compiled_audit01/inspect.py`. Exit0 observed in tool result chunk `9d73f9`; no reference execution. Result SHA `69534a528c93f51ec0b6dae984080b6d1792d6726e144ac8f15a5bb2e4c656c4`.
- 222 input/artifact pins unchanged. Source review and final artifact review are separate, both by Averroes; no repeated Host/compile was needed.

## Preserved Scope

Original binary-equivalent reconstructed C, original e32/m2 assembly and640 uint32 FP golden patterns. This is not byte-proven original C or Linux replay. Complete35ops/3seeds/5985-call order, RNG64 steps/seed, CAP64/physical2 and gather index32 valid. Full383040 results,11970 uint32 guards and5985 returned-vstart checks; no original fflags oracle is claimed.

Expected values use1499 distinct64B blocks and five uint16 IDs per call,155786B total ROM. Calls are not deduplicated. Actual output is264B,33 complete8B stores/reads,197505 output reads over the full history. Word32 at offset256 is element63 plus rear guard. The final block's56B padding is ROM-only and never accessed through out. Original1026-word backing and complete original mismatch fallback remain.

Both compiled ELFs prove128 ordered FP SW per call, interleaved a[i]/b[i], including every no-op/equal-old-value call:241920 total. Each mask group has16 ordered zero SD before original cumulative selected SB:35280 SD and77175 SB total. Mode paths include the compiler's shared mode1 tail. Physical mask128B, actual vlm8B; upper120B cleared.

Both ELFs contain458 exact original helper instructions and no additional RVV. SoC text8340B, rodata160024B; reference-backend text8424B, rodata160032B. Main frame336B. SoC/reference bss-to-stack gaps867624/859232B, retaining at least64KiB stack.

## Cost and Review

Actual linked-reference CFG mandatory core2180430 instructions; positive-path upper2342335 including loop/control unions, RNG/cache, BSS and20000 bounded successful runtime allowance. Headroom657665 to3M. This is a static positive-path bound, not measured retirements or a DUT wall-time guarantee. Failure fallback and terminal parking are not included in that successful-path bound.

Final independent review: `../e32_m2_scalar_source_review01/COST_FINAL.md`, SHA `4e6927a67a56da4710e53078885db33f4d53fe76194d9ff192aba68dd62f179c`, NO_BLOCKER. It binds this exact cost result, two ELFs,30 Host outcomes and222pins. Future reference needs its own exact entry/observer and explicit authorization; this preparation stops here.
