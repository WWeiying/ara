# e32/m2 Scalar Candidate Independent Source Review

2026-10-14: SOURCE_NO_BLOCKER for the exact static candidate below. This is not COST_PASS, compiled-artifact acceptance, or authorization for Host, compilation, Spike or DUT execution.

Candidate: `../full_e32_m2_scalar_candidate01/CANDIDATE.json`
SHA256: `635f20f10c2d16db43ce57e12b7f1b6a8ffc32bdb3d1a3f62320f1a50b61829d`.

## Findings

No blocking source-semantic discrepancy found. The candidate makes two explicit scalar setup optimizations, FP refresh expansion and mask selected-index expansion; their savings must not be attributed to FP caching alone.

- All seven candidate/source pins were independently rehashed and match. `scalar_setup.h` SHA is `12dea4d7c5b857ca58a6305fc3a3032b9c000c1c62f8e186ad43fd7bf6e4d5b5`; `SOURCE_PLAN.md` SHA is `5fa7b86800ab8b29d1e030019e541741b607877ebd6d73e608cf3bc7827b93c7`; integrated C SHA is `b94bc254f01c78d38d6e272a43da2ecf100bd517bcb0afcd5fb62f420494a305`.
- Cache identity is exact: q[k] = fp_inputs[(seed+k)%8]. At i=8*j+k, a uses q[k], b uses q[(3*k)%8]. The latter permutation is 0,3,6,1,4,7,2,5. This preserves the original integer FP bit patterns without floating evaluation.
- Cache preparation follows original per-seed RNG initialization and only writes its separate eight-word local array. The original FP branch remains inside every trial. All 64 expanded pairs are present in ascending order, each a assignment followed by b assignment, with a volatile empty assembly memory clobber after EACH assignment. Thus the requested 128 separate source writes remain per FP call, including VL0 and unchanged values: 1890 calls and 241920 writes. No seed-only refresh replaces the per-call stores.
- SEW32 and CAP64 guards qualify specialization. The a/b uint32 accesses remain within their original backing, with no type punning or new alias promise. All q indices are bounded and their constant modulo expressions need no runtime division in a successful lowering.
- The 16 memcpy zero spans exactly tile mask bytes 0..127, each with a separate compiler barrier. Only after them do mode branches perform ascending original selected indices: 64, 32 and 9 updates. Every selected operation retains its byte read/OR/write and barrier, including repeated writes to the same byte. The total remains 77175 selected updates across 2205 groups. This is not copying a final mask or merging its updates.
- Independently compared the failure function and the entire source suffix beginning at the original helper call: both are byte-identical to reconstructed_oracle.c. Original RNG, loop order, full oracle and fallback are retained. The original 5985 calls, 35 operations, 383040 results, 11970 guards and vstart checks are not reduced.
- Packed output integration is deliberately NOT implemented in this candidate. Its future contract remains all 264 bytes / 33 whole words, including element63 and the rear guard in the last word. This report does not claim an implemented or measured packed oracle.

## Cost And Later Gates

The documented arithmetic is consistent: 4432804 - 1814400 - 1347255 + 544320 + 192 + 244755 + 239400 = 2299816. The additional 250000 allowance gives 2549816. Both are hypotheses based on prior compiled m1 paths, not proved upper bounds or measured m2 costs.

Reloading the cache before every SW is included in the FP estimate; memory clobbers do not justify assuming cached registers survive. Setup/spills, actual mask addressing/dispatch, dictionary indexing, full oracle reads, output fill, original fallback and ABI costs still require inspection. A fixed allowance cannot replace that inspection. The 2-4KiB text growth and stack fit are similarly planning estimates.

The source barriers have an empty template, not a hardware fence. They are an appropriate mechanism to prevent eliminating/combining the intended memory events, but source inspection alone does not prove emitted instruction widths or ordering. Later authorized artifact review must establish 128 ordered SW per FP call, complete mask clear before selected byte stores, actual 16-SD lowering/alignment, no merged source SD, no extra RVV/fence, full output/guard access, map/stack safety and complete CFG cost <=3M. No such execution is authorized by this review.

Only text, JSON, hashes and static list/suffix comparisons were inspected. No Host test, compiler, reference, simulation, live process or raw trace was run/read. Original sealed files and RTL were not modified.
