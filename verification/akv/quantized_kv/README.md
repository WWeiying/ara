# Quantized KV capture admission preparation

This directory currently contains a read-only layout inspector, not an
accelerated Attention implementation. Q4_K_M model weights do not identify the
actual KV type. Inspect the original quantized tensor metadata and binary.

```sh
python3 -B -m unittest discover -s verification/akv/quantized_kv -p test_layout.py -v
python3 -B verification/akv/quantized_kv/layout.py \
  --tensor <actual_attn_k_input.json> --mask <same_query_f16_mask.bin>
```

The bounded first policy supports actual q4_0 and q8_0, 32-element blocks,
up to D256, one batch and a visible zero/-infinity prefix. It checks every
stored row's disjoint byte range, actual token/head strides, binary extent and
finite scales of visible blocks. It does not read hidden row scales: masked
cache storage may be uninitialized and must not become new hardware input.
Both head-major and token-interleaved layouts are accepted when disjoint.
The report lists exact visible candidate ranges and full-gather read+write
bytes; these are not measured bus traffic or a demonstrated speedup.

Synthetic host tests passed for both formats/layouts, 65-visible-token tails,
bad strides/overlaps/extents/types, nonfinite visible scales and unsupported
mask holes. These fixtures are deliberately not claimed to be model captures.
The output status explicitly says layout admitted but not numerically validated.

## Capture-source review

The existing `llama-format-capture-host/bin/llama-completion` accepts
`--cache-type-k q8_0|q4_0` and `--cache-type-v q8_0|q4_0`; its CMake home is
`/home/wangwy/llama/llama-q4km-extract`. That source's `write_tensor` copies
`ggml_nbytes` and records type, shape and byte strides. Its Attention output
callback recovers scheduler-elided K/V views from the graph. This is suitable
for collecting actual cached bytes without first converting them to F16.

However, the source is dirty and its correspondence to the existing binary
must be pinned or freshly built in an independent directory before treating a
new capture as reproducible. The old `normalize-attention-capture.py` explicitly
requires F16 and reconstructs tight F16 strides. Do not use it for quantized KV.
Preserve the original view bytes/strides instead of silently applying that
normalizer or relabelling a F16 capture.

Still required: actual model capture, production-RVV Query Q8_0 bytes and dot
scores, numerical-order comparison with QBS, and original quantized-V F32 PV
plus complete Attention timing. There is no QBS/AKV native quantized-KV or
GGML deployment acceptance from this inspector alone.
