# Integrated e32/m4 Source Review

Verdict: SOURCE_NO_BLOCKER; CONSTRUCTIVE_COST_QUALIFIED_NOT_ADMITTED. Exact source supports a plausible inexpensive scalar-lowering hypothesis for the parent's next-stage decision. No Host/compiler/reference/DUT execution is authorized by this review. Actual cost remains HOLD.

## Accounting Qualification First

CONSTRUCTIVE_COST.md's105*12 outer term describes VL-array/length transitions, but105 is seed*op count; the actual sequence has735 VL groups. The2205*8 group allowance describes trial/mode handling and does not explicitly assign the missing VL selection/advance work. I requested an explicit separate accounting note rather than assuming this work is free. This is a cost-document gap, not a source semantics defect. Merely adding a hypothetical12*735=8820 would give2845347 rather than2836527, but neither figure is an actual GCC upper. The explicit future schedule must account for these operations and any lowering differences.

## Exact Reviewed Source

Root: ../full_e32_m4_integrated_source_proposal01/. All37 STATIC_BINDING pins freshly match. Actual case.c retains the original full nested seed/op/li/mode/si sequence, RNG assignments, helper invocation/vstart clause and full typed fallback. Capacity128 is checked before fixed-shape routines. checks<5985 guards ID-row access, and final count must equal5985. No shortened predecessor sequence, source FP reset or fflags oracle was added. Runtime is explicitly a future standalone replay backend, not Linux ABI.

The actual fp_period.h has eight fresh volatile uint32 table reads inside each op>=25 call. Its three literal seed mappings match (i+seed)%8 and (3*i+seed)%8; sixteen macro expansions at0,8,...,120 each emit a0,b0,...,a7,b7 four-byte memcpy stores with barriers. This preserves256 ordered SW obligations per FP call/483840 total, including empty/equal-data cases. Addresses stop at a[127]/b[127]. The next seed still reexecutes128 RNG steps and overrides. Actual SW width/ordering and clone/ABI behavior remain ELF checks, not claims from this C alone.

The included constant-mask header is the previously reviewed exact header. Its full128B clear and128/64/18 ordered selected-byte sequences are unchanged. Its exclusive-writer premise remains required in the future runtime/layout. There is no selected LBU-retirement identity claim and no change to other sealed shapes.

## Expected Cache And Actual Reads

packed_cache.h declares const uint64 blocks[2252][8] and uint16 IDs[5985][9]. gold_data.S uses read-only data with8-byte block alignment and2-byte ID alignment and incbins the pinned model payloads. Independently checked all53865 existing IDs fall in0..2251. Bounds are established by these immutable payloads, not a runtime check of arbitrary external IDs; any later substituted blob requires its own exact identity/range proof.

Cache c0..c7/tag are local to each invocation. The first fill is unconditional, so no cross-call cache survives. Each later tag equality refers to identical immutable64-byte blocks, and actual data never fills the cache. An ID miss refreshes all eight expected values. The ninth ID reads only one expected word.

All65 actual accesses use memcpy of8 bytes and a volatile empty asm consuming the loaded value, even after mismatch becomes1. Each mismatch assignment is sticky, with no early return from the sequence. Full blocks access0..511 and the last read512..519 contains element127 plus rear u32 guard. Initialization similarly writes exactly65 words with0000005b0000005b, not bytefill, e64 sentinel or padded576B. out is8-byte aligned; byte-based memcpy avoids uint32-to-uint64 alias casts. Expected objects and mutable arrays are distinct. Actual linker placement and lowering must confirm these properties later.

After full comparison, nonzero mismatch executes the unchanged original per-element/guard fallback and diagnostic error counting; a zero mismatch increments elements bycap. The original returned-vstart failure occurs before comparison and remains sticky in errors. Early unequal data cannot bypass remaining65 actual reads, and no actual-result cache is introduced. This source-only implementation is not yet validated by Host mutation execution.

## Constructive Schedule, Not Compiler Evidence

The cache subtotal1072047 is arithmetically consistent with65 actual loads/comparisons per call,9 ID loads,14757 full-block fills,5985 final-word fills and41895 later tag decisions. A hypothetical15 caller-saved-register leaf allocation can hold eight expected values, actual temporary, ID/address and bases/tag/mismatch; this demonstrates no intrinsic need for a stack cache, not GCC's choice. Branch-based comparisons retain all reads on mismatch; alternative XOR/SNEZ/OR lowering has different costs.

Other terms retain all389025 output SDs,483840 FP SWs,154350 selected SBs,35280 mask SDs and77805 original helper instructions. Caller, seed, driver/frame and runtime allowances are explicitly proposed, not measured. In addition to the VL accounting issue above, actual compiler spills, nonleaf transformations, constant/base materialization, backend initialization and register pressure must replace these assumptions in a complete actual CFG/map audit. Old3.699M relative analogy is not used as this algorithm's cost. No software obligation may be removed if actual lowering exceeds3M.

## Identity

- SOURCE_PLAN.md:64731214bef55b769522f83f2584a11fda8caadd8cb24c6b76c4209c425bbe2f
- STATIC_BINDING.json:884fc38a56ff96d595d2040774803d7c8879cb6b8efce9ab45fcc2fd8660e55c
- case.c:17538d5e2c06d93bce644f542792f3b4e9cc4e3cc5a6c2cfeac9845765ac2a97
- packed_cache.h:19218742c1545fb1a62103fd7ac680ca7468e00eeefc036cc72bf27df2aa0228
- fp_period.h:9fd2f317e4b48732d0585658012ee228845683f0c0539895f712d224fbbb007c
- CONSTRUCTIVE_COST.md:5161ce1bc1e433adc1be54d72b0e0a2e1e1f318cb056879358e64f6db3e120c9

No producer file, sealed artifact, running task or RTL was changed. Only static source/metadata/hash inspection and an ID-range read were performed.
