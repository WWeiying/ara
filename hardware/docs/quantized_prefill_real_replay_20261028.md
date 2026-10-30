# Real-data quantized Prefill scheduling checkpoint

## Purpose

The bounded causal-row scheduler shares value decoding between query rows
that use the same KV head. It keeps each row's token traversal and online
softmax accumulation order unchanged. This is a software scheduling prototype,
not a new instruction or RTL modification, and is not yet enabled in GGML.

## Captured workload and checks

The input is an actual layer-0 Qwen3-1.7B-Q4_K_M Prefill capture, with 20 query
tokens, 16 query heads, 8 KV heads, head dimension 128, and KV capacity 256.
Causal visible prefixes are 1 through 20. Keys are independently captured as
Q4_0 and Q8_0; values are Q8_0. These are runtime quantized buffers, not an
offline conversion of a floating-point capture.

Each group contains four query tokens and two query heads sharing a KV head.
The replay uses GGML's quantizer, quantized dot products, dequantizer, scale,
and multiply-add helpers. Only scheduling changes. The host CPU backend must
be initialized before using its FP16 conversion tables; the first draft of
the standalone replay omitted that initialization and failed the golden
check. Adding `ggml_cpu_init()` corrected the harness without changing the
algorithm or the preselected `2e-5 + 2e-5 * abs(reference)` tolerance.

| Key/value format | Outputs checked | Old/new schedule | Maximum absolute golden error | Old V decode calls | Shared V decode calls |
|---|---:|---|---:|---:|---:|
| Q4_0 / Q8_0 | 40,960 | Bit-exact, identical floating-point flags | 5.96046448e-8 | 3,360 | 480 |
| Q8_0 / Q8_0 | 40,960 | Bit-exact, identical floating-point flags | 5.96046448e-8 | 3,360 | 480 |

Both paths evaluate 3,360 valid QK score elements. Masked positions are not
submitted to the dot callback. Output padding is checked for accidental
writes. Sharing reduces value decoding by 85.71% for these shapes, but that
is **not** a cycle reduction or speedup measurement. Host callbacks still
invoke individual GGML dot products rather than native grouped QBS commands.

## Reproduction and next gate

Run from the verification worktree:

```sh
python3 verification/akv/quantized_kv/prefill/run_replay.py \
  verification/out/quant-prefill-real-replay-NEW
```

The output directory must not exist. The runner checks the immutable capture
audit, records compiler/header/library/input hashes, preserves commands and
logs, and rechecks inputs before declaring PASS. This replay is intentionally
specific to the captured shape; the existing synthetic scheduler tests cover
other lengths, dimensions, partial tiles and callback failures.

Next, implement the bounded RISC-V adapter with native QBS grouped QK and
measure the complete call against the old schedule in VCS. Only reproducible
complete-call benefit justifies production admission and dispatch changes.

## Parallel projection integration acceptance

The normal-library model run `m4-packed-normal-model-20261028-01` finished
with PASS: six paired comparisons and 911,616 logits checked. Actual M4
preparation executions fell from 386 to 220, with 166 cache hits. This is
functional/activity evidence, not model timing. A separate Attention audit
also passed: per configuration, 112 Decode calls completed, while 56 Prefill
calls retained shape fallback; dispatch activity was identical in both modes.
Consequently, this model run does not validate the new Prefill scheduler or
native AKV execution. Those remain separate gates.
