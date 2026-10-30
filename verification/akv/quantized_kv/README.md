# Quantized KV capture admission preparation

This directory contains capture/layout inspection and a bounded QBS-versus-RVV
numerical inquiry, not a deployed accelerated Attention implementation.
Q4_K_M model weights do not identify the
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

Still required: target-produced Query Q8_0 bytes and dot
scores, numerical-order comparison with QBS, and original quantized-V F32 PV
plus complete Attention timing. There is no QBS/AKV native quantized-KV or
GGML deployment acceptance from this inspector alone.

## Fresh real-capture worker

`capture_host.py` now builds an independent host `llama-completion` from the
existing capture source and then requests two actual model configurations:
K=Q8_0/V=Q8_0 and K=Q4_0/V=Q8_0. The original source, old binary/build and
existing captures are not edited. It records observed tracked/untracked source
bytes, dirty-source provenance, model/prompt/tool hashes, fresh binary/shared
libraries and build configuration. Source or artifact drift is a failure.

```sh
python3 -B -m unittest discover -s verification/akv/quantized_kv \
  -p test_capture_host.py -v
python3 -B verification/akv/quantized_kv/capture_host.py \
  --output <FRESH_BUILD_AND_CAPTURE_DIRECTORY> --jobs 16
```

Two synthetic validation tests pass, including actual-type mismatch and
nonfinite golden rejection. The independent worker completed both real model
captures in `verification/out/akv-quantkv-host-capture-20261024-01`.
Source, executable, shared-library and tensor hashes were independently
rechecked. Both captures have D128, twelve Query heads, two KV heads,
128 visible tokens and capacity256. Actual K token strides are136B forQ8_0
and72B forQ4_0, so these captures admit direct rows without a gather copy.
This does not establish the layout of every model/cache configuration.
Receipt: `verification/akv/results/quantized-kv-real-capture-20261024.json`.

This is host reference-data collection, never a substitute for VCS cycle
measurements. Even a successful capture does not provide production-RVV
quantized Query bytes or prove QBS numerical compatibility; those remain
separate steps. The current F16 native experiments remain frozen and are not
silently extended to these quantized cache types.

## Actual target primitives

`build_rvv_primitives.py` compiles the whole untouched current production
`arch/riscv/quants.c`, rather than copying/reimplementing three functions.
The GNU bare-metal RV64GCV/Zfh/Zvfh object and the actual disassembly for
`quantize_row_q8_0`, `ggml_vec_dot_q4_0_q8_0` and `ggml_vec_dot_q8_0_q8_0`
are archived under `verification/out/akv-quantkv-rvv-primitives-20261024-01`.
All three contain actual RVV instructions, not generic fallback.

With the explicit O3/no-fast-math/ffp-contract=fast contract, Q8_0 executes a
scale multiply then fused integer-dot accumulation. Q4_0 executes integer-dot
times the first scale, then a fused second-scale accumulation. These are
different rounding orders; inspect actual code rather than assuming all K
formats match QBS. Changing compiler contraction may change this observation.
Receipt: `verification/akv/results/quantized-kv-rvv-primitives-20261024.json`.

```sh
python3 -B verification/akv/quantized_kv/build_rvv_primitives.py \
  --output <FRESH_PRIMITIVE_BUILD_DIRECTORY>
```

The linked numerical ELF now calls those exact compiled primitives with each
capture's own real Query/K bytes, at heads0/6 and tokens0/63/64/127. Its worker
and host replay are described in `rvv_qbs_README.md`. The sixteen-score inquiry
passed native execution and independent raw-log, host QBS replay, work and UVM
rechecking. No score/flag differences appeared in those samples. This is not
all-head, multioutput or complete Attention acceptance; the separate40-command
all-head follow-up ELF has only been built. Neither the inquiry nor its host
tests prove complete Attention performance.
