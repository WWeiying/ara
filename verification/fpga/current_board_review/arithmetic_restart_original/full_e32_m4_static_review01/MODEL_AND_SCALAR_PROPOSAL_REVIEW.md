# Model And Narrow Scalar Proposal

Verdict: NO_BLOCKER_SOURCE_MODEL_AND_CONDITIONAL_SCALAR_MATHEMATICS; COST_HOLD.
Reviewed the actual source_model01 model, construction result, reuse report, receipts and artifact identities. The proposed new constant-mask-store implementation has not yet been inspected as a frozen C/ELF artifact. This verdict establishes mathematical premises for that static source plan, not implementation acceptance or permission to run Host/compile/reference/DUT.

## Actual Model Evidence

source_model01/execution.json records one actual child0/no timeout,5.880765664856881s. All16 input pins and all result-listed generated artifact sizes/hashes freshly match. Read model.py, including distinct source-style and mathematical integer operations/RNG/output construction, original FP table extraction, full tuple expansion, dictionary reconstruction and reuse accounting; did not rerun it.

Actual generated result620787e985a2e829b70dbee457f67bac3d7e14d31afbc0b5bea1b25c53aac4eb reports5985 calls/35ops/3seeds,766080 results+11970 guards=778050 compared uint32 words,1890 FP calls/483840 ordered SW obligations,1104 source seed assignments,2205 mask groups/154350 selected SB. It keeps the original source order, RNG truncation, CAP128 gather/slide boundaries, reduction/compress and FP bit-table indexing. The two Python formulations share the authenticated FP table and do not establish compiled-C or RVV execution. vstart/helper/read counts here remain obligations, not measured retirements.

Canonical blocks are interned by complete64-byte equality, not hash-only equality. Actual U2252 yields144128B dictionary +107730B uint16 IDs +2976B masks/FP constants =254834B listed ROM. Every nine-ID reconstruction is compared against the complete520-byte source/math output. Ninth block has8 valid bytes and56 ROM-only padding bytes. Planning envelope422930B is not a linker map, stack proof or measured allocation. No call is deduplicated.

Reuse result edccb19594976ca3bb7503eba2990b6b2283f88d459b5cf5e81fa4794425353c records33123 adjacent full-block hits,14757 full-block loads and5985 final-word loads:14757*8+5985=124041 expected LD, versus389025 uncached. Ideal120393 is only a benefit bound. These are model access obligations, not emitted instructions.

## Immutable Expected Cache

The proposed one-previous-block cache is semantically valid if reset/invalidated at each call and refreshed on ID change. Invariant: immediately before each comparison, cache[k] equals the corresponding eight bytes of dictionary[current_ID]. Exact canonical-ID equality permits expected-value reuse; it does not permit reusing an observed output value. Dictionary/IDs must remain immutable and disjoint from a/b/out/mask and mutable cache storage; validate index bounds and actual linked identities later.

Regardless of cache hit, retain all65 distinct actual output reads per call,389025 overall. The last read is bytes512..519, containing uint32 element127 AND uint32 rear guard; the first contains front guard AND element0. No576-byte rounded access. Accumulate mismatch across the full reads, then invoke unchanged original typed fallback/counters/diagnostics; do not short-circuit remaining actual reads or cache actual data. Successful expected caching is bitwise, including NaN/signed-zero representations, not a float comparison. C memcpy/scalar lowering and register/spill behavior remain future obligations.

## Constant Selected-Mask Stores

For each mode, let selected positions in increasing order be i_0..i_(n-1), and initialize all128 mask bytes to zero. Define the kth stored byte value:

    V_k = sum(1 << (i_j % 8) for j <= k if i_j // 8 == i_k // 8)

Each selected bit appears exactly once. Inductively, the original LBU/OR/SB at step k reads precisely V_(previous writes to this byte), ORs the next distinct bit and writes V_k at mask+i_k//8. Therefore a constant SB of V_k at that exact address/order has identical state after EVERY selected write, not only the final mask. Values are0..255; shifts0..7. Mode0 selects128 positions, mode1 selects64 odd positions, mode2 selects18 positions2,9,...121. Each mode occurs735 groups, yielding154350 ordered SBs. Full128B zeroing remains every group; upper112 bytes stay zero. This is not final-mask copying, skipping duplicate writes, merging SBs to SD, or reusing a previous group's mask.

Necessary exclusivity premise: between group initialization and completion of its selected SB list there is no other CPU/hart, signal/interrupt handler, DMA engine, RVV instruction or aliasing scalar store writing mask. Original single-thread source executes mask construction synchronously before helper calls; original assembly loads v0 through vlm.v but stores vector results only to out, not mask. Arrays are separate static objects. Thus no competing writer is present in the reviewed source. The future standalone runtime must preserve that premise and its non-aliasing layout; this is not a claim about arbitrary Linux signals, asynchronous shared-memory use or behavior under faulty memory.

Observer obligations must follow the new implementation: verify full clear, exact selected SB address/value/order and helper predicate/result context; do not claim eliminated mask LBU retirements still occurred. Any future compiler barrier/volatile strategy must prove actual separate SB lowering and no added RVV/fences. Changing redundant scalar reads is not original instruction-byte identity. Existing sealed e64/m4 and e32/m2 expected-LD or mask-LBU contracts remain untouched.

## Cost And Next Boundary

Caching eight expected words can spill; hit branches, IDs, address formation and cache updates must be counted. Constants may cost materialization/load instructions, and preserving154350 SBs is mandatory. Removing abstract LBU/OR work is not an actual GCC saving. Existing3384640/3699825 analogies are neither measured bounds nor a basis to waive3M. Source model equality plus these induction arguments do not prove firmware or <=3h runtime. Cost remains HOLD; only the next static source plan is supported here.

Evidence hashes: model.py920b1110cc5114b8582ca3a42080f0ac41fbf6d78176ecb0f2ab8a7a86d43ae8; execution.json5e44dab9f42c0de387b224f2b62041a38a958f5404a29822ed2a118308b1e111; generated01/input_pins.json6a720b35c04c43f975938bae9962c552700c25b4accacb57ae46fad2c92e5057. No producer or sealed file was changed.
