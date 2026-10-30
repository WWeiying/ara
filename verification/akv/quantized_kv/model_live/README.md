# Real Model Generation With Quantized Attention

This is a native-QBS Linux QEMU functional gate, not an RTL or end-to-end
performance measurement. It follows the accepted real-data GGML graphs and
persistent projection/Attention/projection lifetime test.

## Controlled Comparison

- Model: the unchanged Qwen2.5-1.5B-Instruct Q4_K_M GGUF, all28 layers.
- Prompt: `The quick brown fox`, tokenized by the actual model vocabulary.
- One CPU worker, context128, Flash Attention enabled, no GPU offload.
- K cache: Q8_0 and Q4_0 in separate contexts; V cache: Q8_0 in both.
- Baseline and candidate both retain native QBS projection and its existing
  context policy. Only the candidate enables the new quantized Attention hook.
- Each context independently generates three greedy tokens. No hidden-state
  slicing, substituted captured tensors, teacher-forced replacement or sampler
  randomness is used. The candidate consumes its own generated tokens.

Comparisons require all three token IDs and pieces to match. Earlier equality
establishes the common prefix for each subsequent complete-vocabulary logit
comparison. The test reports maximum absolute error, RMSE and distribution KL.
It does not reinterpret a three-token check as a perplexity or model-quality
benchmark. Nonfinite logits, early EOS in this controlled prompt, changed greedy
trajectory, failed model execution or missing native dispatch do not pass.

## Actual Dispatch Evidence

For each format, the prompt is a multi-token batch and uses ordinary quantized
Attention. The next two single-token steps must use the new entry in all28
layers:56 native calls per format,112 total,448 QBS QK command attempts. Reports
must match the actual visible-token count and the two KV groups. A successful
generation that silently falls back for Decode is not acceptance.

The checker also requires positive native Q4_K and Q6_K projection summaries,
with no software emulation. Reserved records use strict full-line matching and
fixed order; seven mutation tests cover missing work, fallback, false PASS,
wrong tokens, altered metadata, invalid metrics and failed guest status.

## Reproducible Execution

`run_model_live.py` pins the accepted interleaving inputs plus actual model
sources, vendor headers, checker, compiler configuration, GGUF, disk and guest
program. It verifies the model file inside the read-only ext4 disk by streaming
it through host `debugfs` and comparing its SHA256 and byte count with the host
GGUF. A matching filename alone is insufficient.

The initial private build is reusable. If still running, the worker waits on
its exact process handle before performing an incremental build; it never
launches two builders into the same directory. A transient user service owns
the complete worker and QEMU child. The QEMU phase has a one-hour default bound.

Build: `verification/out/akv-quantkv-model-live-20261024-01/build`.
Result: `verification/out/akv-quantkv-model-live-20261024-01-control`.
The result is pending until its original logs, dispatch counts, paired logits,
model identity and final input hashes pass. No performance number is inferred
from QEMU wall time. Other prompts/models, long contexts, logits-quality suites
and native RTL timing remain separate gates.
