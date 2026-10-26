# Q8_K runtime preparation: measured activity and next boundary

The accepted signed-max model gate contains real GGML lifetime traces, not
just isolated kernels. The log is
`verification/out/q8k-signed-max-model-20261026-01/qemu.log`, SHA256
`814cfbedd1585227151cbaefcc40544a6ec7760b5d675d985b9b91ab86f3bf9a`.
`verification/qbs/analyze_prepare_reuse.py` checks sequence completeness,
matching source/epoch/layout fields and reconciles counts against the runtime
summary. QEMU elapsed times are deliberately not used as hardware performance.

The OFF and ON modes select the M4 preparation implementation; both retain
QBS and cross-operator context reuse. Each mode has the same activity:

| Input layout | K | Quantizations actually executed | Exact-byte duplicate candidates |
| --- | ---: | ---: | ---: |
| Single row | 1536 | 568 | 224 |
| Single row | 8960 | 114 | 0 |
| Four rows | 1536 | 332 | 166 |
| Four rows | 8960 | 54 | 0 |
| Total | | 1068 | 390 |

An additional 114 quantizations were already skipped by hardware-context
reuse. Do not count those again as potential software-cache savings. The
390 candidate calls produced 1,555,776 duplicate bytes out of 6,694,392 bytes
prepared. All matches refer to the preceding *quantization record*, not
necessarily the preceding graph node. The runtime trace producer uses a full
byte comparison after its digest and identity checks; a repeated pointer
alone would not establish equal data.

The duplicate candidates are concentrated in these consumers (per mode):

| Consumer | Single-row duplicates | Four-row duplicates |
| --- | ---: | ---: |
| Attention V projection | 112 | 56 |
| Attention K projection | 112 | 56 |
| FFN up projection | 0 | 54 |

Thus single-row FFN gate/up reuse is already represented by the existing
skip mechanism; the remaining single-row opportunity is Q/V/K preparation.
This is specific to the recorded graph, not a claim about all model families.

## Why the current mechanism does not remove every duplicate

`arch/riscv/qbs.cpp::context_identity_for_node` requires one input row and a
supported hardware-context plan. `next_context_consumer_matches` additionally
stops on possible input writes, expert operations and incompatible matrix
consumers. `repack.cpp` skips preparation only if context acquisition returns
reuse. Four-row preparation is therefore outside this mechanism. Some
single-row duplicates can also fall outside its conservative lifetime rules;
their exact rejection causes need per-node attribution before changing gates.

The log includes `CONTEXT_BARRIER op=ROPE reason=may_modify_activation`
records around Decode attention consumers. That message is emitted during
lookahead and has no current-node identity, so its proximity to a quantization
line does not prove which failed reuse it explains. A future attribution
probe must include current node, examined next node, source extent, write
extent and rejection reason, including unsupported matrix consumers. Do not
remove the ROPE barrier based on these aggregate byte matches: graph arena
reuse can make a later ROPE destination overlap an earlier input legitimately.

The hardware context and a possible software prepared-buffer cache are
different mechanisms. Removing the one-row restriction from hardware-context
selection would not safely implement a software cache or increase SRAM capacity.

An executable planner probe (`verification/qbs/q8k_decode_sums/context_probe.c`)
checks 48 combinations against the current SDK with its VLEN1024 reference
capabilities: Q4_K/Q6_K, M1/M4, N256/1536/8960, K1536/8960 and unsegmented/
256-block-segmented storage. All checks passed. The 12 M1/K1536 combinations
are context-eligible (1,752 bytes); all tested M4 and K8960 combinations exceed
the 4,672-byte capacity. Thus ordinary planner shape/capacity policy alone
does not explain missing M1/K1536 Q/V/K reuse. This is a host planner check,
not a new native capability measurement or proof that graph lookahead admits
those nodes. Keep those distinctions when choosing the next optimization.

## Implementation boundary for a future software reuse candidate

1. Prove that the graph input has not changed between consumers; retain the
   existing alias, unknown/custom-op and expert barriers unless their safety
   is independently established.
2. Own the prepared buffer explicitly. Do not assume `params->wdata` survives
   intervening operators merely because the activation tensor survives.
3. Include graph epoch, source identity/storage extent, shape, strides,
   activation packing and quantization mode in eligibility. End-of-graph,
   cancellation and fallback must release ownership.
4. Preserve numerical side effects. Repeated quantization can affect FCSR and
   VCSR; skipping it requires an explicit compatible-state contract or faithful
   replay of its effects, not just cached bytes.
5. Start with one thread and a single bounded entry. Prove interleaved graphs,
   in-place writes and different packing cannot reuse stale data before
   considering wider concurrency.
6. Measure quantization avoided minus buffer-copy/ownership costs on VCS.
   Use complete paired consumers, then real GGML graph/model validation.

This is an opportunity assessment, not an implemented cache or an end-to-end
speedup claim. First finish the two pending Decode preparation measurements;
then decide whether local kernel gains or eliminating repeated preparation
offers the better measured return. Do not enlarge SRAM or relax correctness
gates solely to match these trace counts.

## Private attribution probe

`verification/qbs/q8k_decode_sums/compile_context_attribution.py` now builds
a separate QBS translation unit with lookahead decision records. It does not
edit or install the runtime source. Each record includes graph epoch, current
and examined graph-node indices and identities, source tensor identity, source
address/extent, examined destination address/extent, operation, decision and
reason. Reasons distinguish missing graph, possible input modification, expert
context consumers, ineligible matrix consumers, identity comparison and graph
end. Pointer identities can be joined with the existing lifetime records.

The complete production-flags compile passed in
`verification/out/q8k-context-attribution-compile-20261026-01`. The source hash
was `5de40095e57195b73c642f813ca3f3b7e9e1976d89149d177e5f0df7954ee180`.
The accompanying test reverses all observation wrappers and requires the
original source text to be recovered exactly; double instrumentation is
rejected. This establishes instrumentation scope, not runtime correctness or
performance. No model has yet been run with this probe. Its logging must not
be used for latency measurement. The existing potentially conservative
overlap checks remain intact until a concrete graph-level counterexample and
safe alternative are established.

### First measured attribution, before final model completion

The independent model probe is running in
`verification/out/q8k-context-attribution-model-20261026-01`. Its first frozen
analysis is `verification/out/q8k-context-attribution-analysis-20261026-01`;
the snapshot hash is
`8c4dbe6872406cae1200975018ce0daaeb6c63156c6e0a9266116a6f4638641c`.
This is partial-run attribution, not a complete model acceptance record.

For graph epoch 2, layer 0, the probe establishes these specific boundaries:

| Current projection | Current node index | Examined index | Decision |
| --- | ---: | ---: | --- |
| Q | 3 | 8 | Ineligible intermediate MUL_MAT; destination does not overlap input |
| V | 10 | 14 | Ineligible intermediate MUL_MAT; destination does not overlap input |
| K | 16 | 19 | ROPE destination overlaps input storage |

Thus the ROPE warning is not the reason Q-to-V and V-to-K reuse was rejected.
It occurs after K, where the input allocation is genuinely reused by a later
output. The Q/V boundary is the conservative rule that any ineligible matrix
node may acquire the hardware context, for example through a supported tail.
Before changing that rule, identify these intermediate nodes' weight/input
types, shapes, backend selection and actual context use. Do not simply skip
all unsupported matrix nodes: the existing rule protects context ownership.
