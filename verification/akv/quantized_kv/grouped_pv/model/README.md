# Short Model Grouped-PV Successor

Prepared for parent review. Do not launch before approval. No SDK, external
llama, sibling ggml/, pair/, or frozen original model runner is changed.

## Comparison

Derived from model_live/test.cpp: Qwen2.5-1.5B-Instruct Q4_K_M, 28 layers,
fixed four-token prompt, three greedy predictions, separate fresh contexts for
Q8_0 and Q4_0 K, Q8_0 V. Requested context128 rounds to actual256, as in the
accepted original strided model test. One compute thread, flash Attention ON.

Both baseline and candidate enable QBS projections and quant-KV Attention.
Baseline UNSETS GGML_RISCV_AKV_GROUPED_PV (default OFF); candidate sets it to1.
This is NOT an all-RVV baseline or a new comparison with scalar model inference.
The separately accepted graph02 evidence supplies the reference numerical gate.
Reuse one loaded model but never reuse KV contexts between generations.

Check all vocabulary logits for each of three steps, finite and bitwise equal,
same greedy IDs/pieces, zero max-abs/RMSE/KL. Sample calling-thread FCSR/VCSR
immediately after each llama_decode, before logits/comparison arithmetic.
Start RNE, preset DZ, VCSR5, vstart0; require preservation and exact paired CSR.
CSR is a calling-thread observation, not an aggregate of other OS threads.
Failure diagnostics print actual CSR before failing; no thread2 exception is
introduced into this single-thread contract.

Decode must admit all28 layers for both modes and types: 224 native calls,
896 commands, 448 gathered panels, 256256 copied K bytes, 2464 value decodes.
Every native trace requires grouped=0/1 as appropriate and completed_groups=2.
Prefill may bypass the hook or report all28 shape fallbacks with zero work.
Enable existing QBS_TRACE_CALLS: require identical per-step projection invocation
sequences/work across OFF/ON, and reconcile those calls with existing process
projection summaries. Native Q4_K/Q6_K execution is mandatory, emulation zero.
No cycle, RTL performance, perplexity, long-context or general-quality claim.

## Admission And Execution

graph_receipt.json explicitly fixes the actual terminal PASS graph02 receipt,
log and source-pins hashes. Runner checks terminal status, all current input
pins, replays the current new graph checker, and compares every checked field
against the receipt (including thread-local observations). A preflight-only,
old FAIL, old checker, or merely matching summary counts cannot satisfy it.

external_snapshot.json separately fixes the current adapter, graph snapshot,
and complete rg-visible llama ggml/cmake/src/include/vendor/root-CMake inventory.
Old snapshots are not relaxed. All graph inputs, model/current sources, imported
helpers, own files, toolchain, model, read-only model disk and native QEMU model
receipt/build are pinned. Fresh model ELF/build hashes, init and initramfs are
pinned before guest execution and checked afterwards. Guest model bytes are
stream-hashed through read-only debugfs and matched to the host GGUF. No writable
model disk or shared build directory is used.

Build fresh llama plus production GGML using the original model CMake contract;
do not rebuild or mutate graph02 libraries. Require all compile units and driver
paths to be pinned, native hook enabled and production recurrence flags retained.
No waiting queue, owner polling, retries or historical receipt substitution.
Configure/build/model-disk/init/cpio/QEMU limits: 180/1800/180(+10 kill grace)/
120/60/at most7200 seconds, once each. Direct systemd service ownership is
required for a background run. Capture complete logs. PASS requires every
checker gate and all post-input pins, not just three generated tokens.

After parent approval only:

```sh
python3 -B verification/akv/quantized_kv/grouped_pv/model/run_model.py \
  --prerequisite verification/out/grouped-pv-ggml-20261026-02 \
  --build verification/out/grouped-pv-model-build-20261026-01 \
  --output verification/out/grouped-pv-model-20261026-01
```

--preflight-only validates admission and writes PREFLIGHT_OK without building
or running the model. It requires the same real graph PASS. Use fresh separate
build/result directories; no command is automatically launched by import.

Host-only tests:

```sh
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/grouped_pv/model -p 'test_*.py' -v
```
