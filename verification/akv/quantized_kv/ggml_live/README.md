# Native QBS Quantized Decode In Actual GGML Dispatch

## Scope

The private llama.cpp CPU backend now has a default-OFF build option,
`GGML_RISCV_AKV_QUANT_KV`. It requires the existing QBS and AKV builds. Runtime
selection additionally requires `GGML_RISCV_AKV_QUANT_KV=1`, native QBS opt-in
and the explicit normal-memory policy
`GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=1`.

The new branch is before the existing F16 AKV admission. It handles only
single-worker Decode with the types, dimensions, mask, strides, numerical domain,
buffer bounds and workspace admitted by the shared runtime. The original F16
AKV and ordinary GGML paths remain available. Rejection before execution permits
fallback; execution failure after partial work aborts instead of silently
recomputing. No new RTL or ISA is introduced.

The adapter uses production Query quantization, the accepted finite Q8_0 RVV V
decoder and original RVV F32 scale/mad helpers. Its C runtime retains the tested
floating-point contraction policy; it does not inherit the F16 AKV runtime's
different contraction policy. The QBS bridge accepts only nonsegmented DIRECT
Q4_0/Q8_0 weight with Q8_0 activation and row-major layouts.

## Context Ownership

The existing AKV execution mutex is acquired before the QBS context mutex.
The latter covers the complete quantized Attention task, not only individual
commands. DIRECT does not wait for `reserved=false`, release persistent AQ,
change graph ownership/generation or alter the current cross-operator request.
This avoids a wait cycle when a later projection consumes an existing
reservation. The executor is scoped to the owning thread and rejects context
commands. Ordinary projection context execution uses the same QBS mutex.

This is an integration contract, not evidence of OS context migration or
multi-hart support. Cross-operator interleaving and failure recovery require
their own focused acceptance beyond the graph test below.

## Accepted Functional Graph Test

`verification/out/akv-quantkv-ggml-live-20261024-02-control` passes actual
`ggml_graph_compute_with_ctx` through the installed opt-in operator branch in
native-QBS Linux QEMU. It does not directly call the adapter from the test.
The test loads unchanged real Qwen Query, K/V, mask and captured output bytes:
all12 Query heads, both KV heads, D128, visible KV128 and capacity256.

| K; V always Q8_0 | Native graph calls | Commands per call | V rows decoded per call | Maximum absolute error vs captured output |
| --- | ---: | ---: | ---: | ---: |
| Q8_0 | 2 | 16 | 256 | 1.40070915e-6 |
| Q4_0 | 2 | 16 | 256 | 9.65595245e-6 |

Each call checks all1,536 outputs with the unchanged per-element tolerance,
matches the ordinary graph's FCSR, repeats bit-identically and preserves input
bytes. Six fallback cases cover mask holes, two CPU workers and missing
normal-memory opt-in, for both profiles. Every fallback destination is poisoned
before execution so an old output cannot masquerade as success. Mask-hole
fallback matches the ordinary graph bit for bit and issues no QBS command.

The strict ordered-line checker requires all64 native command attempts,
completed groups, decode counts, fallback boundaries and successful guest exit;
unknown/extra protocol records are rejected. Mutation tests cover missing work,
extra entries, malformed suffixes, bad terminal status and nonfinite summaries.
The runner verifies actual compile-source paths, native feature macros and
enabled test assertions, pins input sources/tools/binary/initramfs, and checks
identity after execution. Raw log and all714 pinned inputs were independently
replayed after PASS.

The earlier `...ggml-live-20261024-01-control` is preserved as INTERRUPTED. It
was stopped to tighten fallback/output and provenance checks; it is not accepted
evidence. The successor reused the same private build directory incrementally
and retained a separate result directory.

## Reproduction And Remaining Gates

The external private checkout is not committed or pushed automatically.
`snapshot_llama_integration.py` exports its complete observed working diff and
the two new adapter files, with hashes and the external base commit. The snapshot
explicitly includes preexisting private changes rather than attributing them all
to this integration step. Apply it only to an independent matching checkout.

```sh
python3 -B verification/akv/quantized_kv/run_live_graph.py \
  --build /absolute/fresh-or-compatible-build \
  --output /absolute/new-result-directory --jobs 16
```

This test proves native functional dispatch of real captured graphs. QEMU is
not a timing model. Public-entry VCS comparisons, actual persistent-context
interleaving and whole-model generation remain separate required gates before
production promotion or a model-level speedup claim.
