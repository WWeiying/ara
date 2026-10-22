# e64/m4 Integrated Proposal Independent Review

2026-10-14: SOURCE_NO_BLOCKER for this exact static proposal. Parent authorization is still required before Host/compile. No actual software artifact, lowering/cost, reference or DUT acceptance is implied.

Input directory: `../full_e64_m4_scalar_source_proposal01/`.

| Identity | SHA256 |
| --- | --- |
| CANDIDATE.json | `e77b93e4c0d7e73793d506f7a3cd39c0f97337fc30442ceb4cf6d68574f9c124` |
| SOURCE_PLAN.md | `61d0f2ac795512a52bd13b7255806675daaa71e78715d397002c1f6c425c4ce8` |
| STATIC_PROOF.json | `ddb44ecc371a669ab6566e8944ec3df6884c1419bacc930fd6d313abd8e25d75` |
| Prior independent SOURCE_MODEL.md | `c2af863f49827f27e59205df2914c7790da43e1c0235c0b78c79ed5f167c2a6d` |

All eight proposal pins and sixteen dependency pins were independently rehashed and match. The model and original-source review is recorded separately; it is not substituted for this integration review.

## Findings

No blocking source-semantic discrepancy found in case_proposal.c, source_integration.diff, mask_setup.h, packed_output.h or the pinned FP-period header.

- SEW64/CAP64 guards qualify the specializations. Original seed/op/VL/mode/start loops, RNG/overrides, helper arguments and returned-vstart check remain. The diagnostic function and full original scalar mismatch fallback were independently compared byte-for-byte. Success adds CAP to elements once; both paths increment checks once. Original first20 diagnostic behavior and uint64 guards are unchanged.
- Every FP trial still calls the periodic setup before output fill and helper execution. Its eight fresh volatile input-table reads and three seed permutations retain all 128 ordered uint64 destination writes a0,b0,...,a63,b63, including VL0/equal values. Memory clobbers follow each store. Actual SD multiplicity, code size, register allocation and spills remain compilation gates, not source-proven machine behavior.
- Independently checked mask clear offsets 0,8,...,120 and exact ascending selected lists 0..63, odd1..63, and 2,9,...,58. Each selected operation is its original cumulative byte read/OR/write, not a final-mask copy. All 128 bytes are cleared before bitsets. Source totals remain 35280 intended clear SD and 77175 selected SB; only actual later disassembly may establish those emitted widths.
- Output initialization spans exactly 66 typed uint64 words with value 0x5b. The comparator uses OR of per-word XOR differences, so two corruptions cannot cancel as in an XOR checksum. Volatile reads preserve all 66 actual and expected observations even on mismatch. Eight complete blocks and two words of block8 cover precisely 528 bytes; the final two words are result63 and the upper guard at offsets512 and520. The 48 ROM-padding bytes are never read from output. All nine IDs participate.
- Typed uint64 output/dictionary access respects the actual object type and natural alignment. Mask clearing uses memcpy into byte storage, not an alias-violating uint64 cast. No restrict promise, host floating arithmetic, new vector operation or hardware fence is introduced by these scalar headers.
- Full scope remains 5985 calls, 35 ops, 383040 results, 11970 guards and 5985 returned-vstart checks. The original 640 FP bit patterns remain golden; no new fflags/frm oracle is claimed. CAP64 gather/slidedown bounds and four physical registers per group must remain in the eventual observer.

## Explicit Unfinished Boundaries

The dictionary and IDs are extern declarations only. Their future emitted definitions must match the already pinned own-shape U1986 dictionary and 5985x9 ID binary exactly. The original Linux syscall/start/finish wrapper is still present and explicitly documented: this candidate is not a runnable SoC adapter. Later runtime adaptation must preserve the proven source/fallback while using the actual backend exit contract.

Three optimizations are separately attributable: mask setup, FP refresh and packed comparison. The new comparator is XOR/OR accumulation with block control, not the earlier illustrative per-word branch model; that old estimate cannot be reused as an actual cost bound. Source reserves and the 240402-byte model ROM arithmetic are not an actual map, stack or <=3M cost result. Actual compiled helper bytes/no-extra-RVV, fresh stores, all66 reads, linked tables, ABI/layout and full positive CFG must be verified before any reference request.

Archive resume03's exact ELF board PASS remains historical evidence only. No current M9 full regression or remaining RTL bug is established by this proposal. This review executed no Host test, preprocessor, compile, model/check script, Spike, VCS, raw trace or live query; only existing text, metadata and hashes were inspected. Producer and sealed files remain unchanged.
