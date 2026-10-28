# Native Prefill complete-call experiment

## Question and comparison

Does sharing V decoding across causal query rows improve the complete call
after accounting for quantization, QK submission, softmax and PV?

The baseline is deliberately not scalar or per-element RVV. It already uses
QBS and shares work between the two query heads of each GQA group. It executes
one query token at a time. The candidate retains the same QBS commands but
shares V decoding across four query tokens. Both use the existing online
arithmetic helpers and retain each output row's token accumulation order.

| Property | Baseline | Candidate |
|---|---|---|
| Source | Actual Qwen3-1.7B-Q4_K_M layer-0 Prefill capture | Same |
| Selected slice | KV head 0, query tokens 16 through 19, two query heads/token | Same |
| Dimension / outputs | D=128 / 1,024 F32 outputs | Same |
| Causal prefixes | 17, 18, 19, 20 tokens | Same |
| QK | Four M2 native QBS commands | Four M2 native QBS commands |
| V decode calls | 74 | 20 |
| Measurement | Query quantization through final drain | Same |

This is a bounded representative slice, not a whole operator/model latency.
It isolates an incremental improvement over existing QBS use. It does not
measure the earlier QBS-versus-RVV acceleration again. The captured full
tensors remain embedded without changing their values or indexing.

## Gates

1. Rebuild all 13 linked objects from current sources and reviewed build
   recipes; preserve compiler dependencies, library hashes and capture audit.
2. Verify the canonical VCS image/source identity and ELF memory bounds.
3. Run ABBA in one ELF. Check all 1,024 outputs on all four trials against the
   captured golden, require bit-exact pairing, check FCSR/VCSR, output padding,
   command counts and value-decoder counts. Golden tolerance is fixed before
   execution at `2e-5 + 2e-5 * abs(golden)`.
4. Independently parse printed output words and run the existing vector/AXI
   protocol checker. A completion marker alone cannot establish PASS.

The independent numerical checker has positive and mutation tests covering
missing completion, bad activity, invalid cycles, CSR changes, NaNs, malformed
trial ordering, wrong golden input and small paired bit differences.

## Commands

```sh
python3 verification/akv/quantized_kv/prefill/build_native.py \
  verification/out/prefill-native-q4-build-NEW --kind q4_0
python3 verification/akv/quantized_kv/prefill/test_check_native.py
python3 verification/akv/quantized_kv/prefill/run_native.py \
  --build verification/out/prefill-native-q4-build-NEW \
  --output verification/out/prefill-native-q4-vcs-NEW --execute-reviewed
```

Without `--execute-reviewed`, the runner performs identity preflight only.
Long runs must be owned directly by a transient systemd user service. The
worker writes status and terminal result JSON and performs the protocol check
after simulator completion. The bounded timeout is three hours. No simulator
performance result is asserted by this design/launch note.

Strided K panel reuse, complete GGML admission and model dispatch integration
remain subsequent steps. The experiment intentionally changes no production
runtime behavior and no RTL.
