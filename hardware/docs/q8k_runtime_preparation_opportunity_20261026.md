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

## Why the current mechanism does not remove every duplicate

`arch/riscv/qbs.cpp::context_identity_for_node` requires one input row and a
supported hardware-context plan. `next_context_consumer_matches` additionally
stops on possible input writes, expert operations and incompatible matrix
consumers. `repack.cpp` skips preparation only if context acquisition returns
reuse. Four-row preparation is therefore outside this mechanism. Some
single-row duplicates can also fall outside its conservative lifetime rules;
their exact rejection causes need per-node attribution before changing gates.

The hardware context and a possible software prepared-buffer cache are
different mechanisms. Removing the one-row restriction from hardware-context
selection would not safely implement a software cache or increase SRAM capacity.

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
