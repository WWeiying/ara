# Stage5 Model Inputs And Held Harness

Preparation only. No model regression, library build, QEMU launch, production
capability change, or hardware/model performance claim is authorized here.
All five pairs remain held until S2/S3 and parent review. This directory owns
new files only; do not patch sealed Stage3/4 helpers or live dirty llama/SDK.

## Matrix

| Pair | Real model weights | KV | Prompt / Decode active contexts | Route requirement |
|---|---|---|---|---|
| smol_f16 | SmolLM2-135M Q4_K_M | F16/F16 | 63 / 64 / 65, capacity128 | D64/GQA3 resident Decode, odd head |
| qwen3_f16 | Qwen3-1.7B Q4_K_M | F16/F16 | 136 / 137 / 138, capacity256 | D128/GQA2 resident Decode, tails |
| qwen25_q8kv | Qwen2.5-1.5B Q4_0 | Q8_0/Q8_0 | 40 / 41 / 42, capacity128 | Existing quantized-KV route; no resident |
| qwen25_q4kv | Same Q4_0 model | Q4_0/Q8_0 | Same tokens and contexts | Existing quantized-KV route; no resident |
| gemma_d256 | Gemma3-1B Q4_K_M | F16/F16 | 4 / 5 / 6, capacity128 | D256 standard fallback; no resident |

Capacity in the table is the requested n_ctx, not the effective allocation:
archived llama-context.cpp pads it to256. The guest must verify and record256
for all five cases. Logical contexts above must also be checked against actual
attention route counters; the harness does not label a calculated length as an
observed active_kv value.

These are real models with controlled token-prefix workloads, not new captured
trajectories. Metadata context limits are inventory only, not tested maxima.
There is no new D96 model, nine-format closure, long-context claim beyond these
contexts, or F16 resident Prefill support. Weight formats and KV formats are
separate axes; tensor-type histograms record mixed Q4_K_M contents explicitly.

## Inputs And Preparation

```
python3 -B verification/performance/next_mechanism/stage5/models/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_models_prepare_20261110_04
```

The fresh output contains archived Ara c49289ff8 and validated llama da56aa750
sources, never unchecked live source copies. The separate03959acc0 native-auto
reference and its two-file diff from common ancestor8ed9403e are archived but
NOT applied. Clean03959 lacks the accepted QBS prepared/cache/packed/sums and
quantized-KV additions in da56; setting environment flags cannot restore them.
The runtime owner must reconcile da56 plus the registered native-auto/compiler
contract delta before binding the selector. Baseline CMake commands target the
validated da56 archive; they are held, not an accepted composed library recipe.
Models stay in place and are SHA256 pinned;
read-only debugfs streaming verifies their bytes inside existing guest disks.
GGUF embeds the tokenizer: all tokenizer metadata fields, complete GGUF and
disk are pinned. No HuggingFace tokenizer files or chat template are applied.

The existing build-prof host llama-tokenize binary and resolved shared libraries are
hash-bound as input preparation tools, not claimed to have a proven source
build identity. It loads vocabulary only and executes no model inference.
The archived GGUF parser inventories model shape and actual tensor formats.
The source paragraph is tokenized with model-required special tokens and
special-token parsing disabled. The exact full list, prompt prefix and two
following teacher-forced tokens are frozen. Before inference the future guest
must independently re-tokenize with its built llama and match the complete
list; mismatch is a hard failure, never automatic retokenization or retry.
Preparation retains tokenizer stdout, stderr and exit status separately. Eleven
host contract tests and five GNU syntax-only checks run; the missing-selector
compile must reject. No objects, linked model executable or library are built.

Attempt01 remains PREPARATION_FAILED: Qwen2.5 tokenization exited unsuccessfully
with empty output through the older shared command wrapper, which did not retain
its exit code. Attempt02 retained SIGSEGV (-11) at Smol vocabulary-only context
construction. A concrete ABI mismatch was then found: build/bin/llama-tokenize
passes 0x22 dwords (136 bytes) at402a74/402a7f to llama_init_from_model, while its
resolved library's default-params function writes through offset0x98+8 (160).
The separately installed build-prof pair passes0x28 dwords (160) at40249a/4024a5,
matching its library. Attempt03 pins that matched set, reported commit853fa38a5,
and retains both disassemblies. No old binary/library or failed output is edited.
Guest re-tokenization remains mandatory: producer build provenance is not a
substitute for validation against the actual guest tokenizer. No numerical gate,
model, token acceptance condition or retry policy is relaxed.
Attempt03 completed input/token/host/syntax preparation using the matched tool,
but retained clean03959 as the runtime reference. It is PREPARED_HELD, not a
baseline acceptance. Attempt04 preserves its outcome and changes the runtime
source inventory to da56 plus the separate registered reference/diff; no dirty
overlay is copied and no reconciliation is silently applied.

`input-manifest.json`, `model-inventory.json`, `held-commands.json`, and
`source-pins.json` are the handoff. `commands.json` records preparation commands
actually executed; held command templates are explicitly NOT executed recipes.
An unresolved QEMU/selector/ELF/counter binding requires a separately reviewed
successor receipt, not edits to these frozen inputs. The old pinned QEMU is
inventory/provenance only: it cannot execute the new resident instructions.

## Comparison And Counter Contract

`model_pair.cpp` follows sums_model_test.cpp: OFF/ON children initialize GGML
independently, but both consume the identical frozen tokens. Three API calls
produce complete last-position vocabulary logits, greedy predictions and
FCSR/VCSR/vstart records. Predictions are compared, not fed back, so divergence
cannot silently change subsequent work. RNE, sticky DZ and vcsr5 are installed
before each call; results must match bitwise with valid CSR state. No precision,
softmax, masking, libm or arithmetic-order substitution is introduced.

Both arms retain the same QBS prepared/cache/packed/parallel-sums settings,
legacy paired Attention, and quantized-KV/Prefill/register-PV options. Only the
reviewed resident selector may differ. An environment switch is NOT a claim of
normal-memory eligibility, loan ownership or advertised hardware capability.
Inherited RVV fallbacks remain available. Historical QBS-versus-RVV tolerance
contracts are separate; they do not relax this resident-only exact comparison.

The harness cannot compile without an explicit reviewed selector binding.
It emits only `STAGE5_NUMERICAL_PAIR_ONLY`, never overall PASS. The successor
checker must consume complete merged guest stdout/stderr and validate native
QBS per-format GEMV/GEMM work, old AKV/quantized routes, resident QK/PV/PV_PREP,
head/group/tile/querybase mapping, fallback reasons and balanced completion.
Logical work must match across arms; primitive route counts need not match.
Require zero resident commands for every Prefill and unsupported Decode; require
positive, exactly mapped commands for eligible candidate Decode. SDK request
logs alone cannot prove actual custom instruction execution. Bind the accepted
instruction-model counters as well. No terminal numerical marker alone closes
S3/S4, and no fallback/retry is allowed after resident command start.

## Resource And Acceptance Boundary

One direct systemd worker, one guest CPU, 4GiB guest memory, MemoryMax4GiB,
CPUQuota100%, 5400-second per-pair ceiling, no automatic retry. No concurrency
increase without parent approval. The preparation has no launch interface.
Estimate 30-60 minutes for the later archived build/preflight and a 4-6-hour
total model budget after S2/S3 readiness, recalibrated after the Smol pilot.
Five-pair completion within that budget is not assumed. Preserve first failures
and stop on source/image/checker drift. QEMU is functional evidence, not new RTL
cycle evidence or a model speedup measurement.
