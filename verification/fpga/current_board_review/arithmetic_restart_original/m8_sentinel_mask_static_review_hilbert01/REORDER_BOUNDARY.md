# Actual Initialization Reorder Boundary

Same-epoch reordering of independent stores to these private, ordinary, nonvolatile arrays is allowed. Source memcpy order is not an architectural instruction-order contract. No concurrent writer, MMIO observer or intervening helper access is assumed. Do not recompile to force the old store order.

Observed actual SoC listing: output initialization is straight-line at8000103e..80001202. Tail SW at80001192 writes offset1024 before the remaining SD offsets800..1016; helper JALR is later at8000122a. Mask SD offset96 at80000ff6 similarly precedes SD offset8 at80000ffc, within the same group. Neither reordering alone is a defect. Actual main frame is304B.

Required whole-CFG proof: every call executes precisely128 aligned SD covering offsets0..1016 and one SW covering1024..1027, exact typed values005b005b005b005b/005b005b, before its helper. Address ranges are disjoint, complete and within1028B; no extra writer or missing/duplicate write. Each original mask group still executes16 aligned SD covering128B with original table values before helper consumption. Source RNG, group/trial/helper and prior-oracle boundaries remain intact.

The observer must bind actual PC/code, decoded address/width and register-derived value in the actual new-ELF order. A final correct shadow, store count or address-set alone is insufficient to prove fresh initialization. No transfer of a write across call/seed/helper boundaries, no helper/mask/RNG phase change, and no deletion of fresh stores is accepted. Previously sealed observers keep their own original contracts unchanged.

This documents the permitted source-semantic boundary, not completed full4095 CFG proof. Zeno has been asked to apply it to both actual backends and report all-path validation without further compilation. No reference/DUT execution authorized.
