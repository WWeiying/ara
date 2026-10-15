# e8/m8 Single Source Successor

Only packed.h differs: ID0 full blocks compare raw words with byte sentinel 0x5b5b5b5b5b5b5b5b; initialize_mask copies the same 128B in sixteen explicit 8B memcpy statements. Original case.c (including fallback) is byte identical. Dictionary, IDs, sequence, helpers, model, input generation and compiler flags are inherited immutable.

Scope: original4095 calls / SEW8 CAP1024 vtype3 physical8. Checked output1026B =128 complete words + separate2B tail. Full128B predicates including high64B remain. Success reads every output word and tail; mismatch still returns to unchanged scalar fallback and original element error totals.

No source sentinel-hoist or savings assumption: actual linked CFG must include constants, literal-pool loads, branches, joins, spills, full main and setup. Compilation once per original backend with fixed flags. Short C/UB tests only, no fullstream Host, Spike/reference or VCS. Actual cost above3M is HOLD; no flags search. Source diff requires independent Averroes acceptance before testing or compilation.
