# GGML Decode Metadata Bridge

## Position In The Integration

`software/akv/experimental/quantized_kv/ggml_decode.h` translates actual
`ggml_tensor` metadata into the existing quantized-KV runtime input. It is an
experimental, header-only bridge, not an installed GGML backend. Neither
`llama.cpp` nor the existing F16 AKV dispatch is changed or enabled by it.

```text
GGML FLASH_ATTN_EXT tensor + caller-verified accessible memory extents
    -> metadata mapping (no instruction issue, no arithmetic, no input scan)
    -> akv_quant_native_execute
         -> one shared capability/layout/mask/data/workspace admission
         -> Q8_0 Query quantization
         -> QBS Q4_0/Q8_0 K x Q8_0 Query, shared across Query heads
         -> existing FP32 online Softmax and RVV PV schedule
```

Mapping success means only that the operator metadata was translated. It is
**not** permission to execute. Keeping the full data admission in the shared
runtime avoids scanning the KV scales twice and prevents a separate GGML
admission implementation from drifting from native benchmarks.

## Exact Shape And Stride Mapping

| Tensor | GGML logical shape | Runtime token stride | Runtime head stride | Inner storage unit |
|---|---|---|---|---|
| Query | `[D,1,Hq,1]`, F32 | `nb[1]` | `nb[2]` | `nb[0]=4` bytes per scalar |
| K | `[D,capacity,Hkv,1]`, Q4_0 or Q8_0 | `nb[1]` | `nb[2]` | `nb[0]=18` or `34` bytes per 32-value block |
| V | `[D,capacity,Hkv,1]`, Q8_0 | `nb[1]` | `nb[2]` | `nb[0]=34` bytes per 32-value block |
| Output | `[D,Hq,1,1]`, F32 | `nb[2]` (only one query token) | `nb[1]` | `nb[0]=4` bytes per scalar |
| Mask | `[at least capacity,1,1,1]`, F16 | one contiguous row | no per-head variation | `nb[0]=2` |

The output head axis is different from the Query head axis. Substituting Query
`nb[2]` for output `nb[1]` silently corrupts padded output layouts. Quantized
`nb[0]` describes a whole block, not one four-bit/eight-bit value; multiplying
that stride by D would also produce incorrect row addresses.

The bridge preserves both ordinary head-major and non-overlapping token-major
V views. The shared selector proves their interval safety. K token rows must
remain tightly packed because the current QBS descriptor has no arbitrary
weight-row stride. Unsupported layouts select fallback rather than copying or
repacking data implicitly.

## Caller Responsibilities And Fallback

The caller must obtain actual accessible byte extents from each tensor's data
pointer and verify normal CPU-addressable memory. An allocation's total size is
not automatically the valid remainder after a view offset. Do not derive a
larger extent from logical dimensions to make admission pass. The input tensors,
metadata, capabilities and workspace must remain stable through completion.

The caller supplies runtime VLEN/vstart/FRM and previously checked QBS device
capabilities. This bridge does not invent hardware support or query a device.
The existing shared selector still checks alignment, overflow, shape limits,
output/input aliasing, finite scales, Query quantization range and exact
positive-zero/negative-infinity mask prefixes. Scalar op parameters are copied
bitwise, so mapping a signaling NaN does not itself raise a floating exception.
Sinks, bias and softcap are forwarded and rejected by the shared feature gate.

The first integration is explicitly single-worker: `nth=1`, `ith=0`, no
`use_ref`, and an explicit requested flag. Multiple CPU workers retain the
ordinary path until collective admission and error handling are designed. One
worker must not fall back after another worker has written part of the result.
Batch and Prefill shapes are not silently interpreted as Decode.

Only `FLASH_ATTN_EXT`, F32 output/Query, the specified quantized KV types, and
GGML default/F32 accumulator precision are mapped. Unknown extra source tensors,
unsupported precision, missing masks and out-of-range signed dimensions are
rejected before any narrowing cast. Existing ordinary RVV/F16 AKV paths remain
available; model names are not used as an admission condition.

Execution status handling must retain the common ABI distinction:

```text
map rejected                         -> ordinary implementation
native FALLBACK (before any work)     -> ordinary implementation
native OK                            -> operation handled
native EXECUTION_FAILED (partial work possible)
                                     -> report execution failure; do not retry
```

The bridge is not yet connected to the live GGML dispatch. Promotion still
requires complete real-Attention numerical and timing acceptance, a measurement
through this shared entry including admission cost, and actual GGML execution.
None of those are inferred from metadata tests.

## Tests

`test_ggml_decode.c` includes the real checked-out `ggml.h`, not a replacement
tensor definition. It constructs tensor metadata and uses the existing QBS
reference capability initializer; it does not claim a hardware capability query
or execute a model graph.

- 2,048 positive combinations: D32--256 in steps of 32; GQA groups 1--8;
  one/two KV heads; visible prefixes 1/31/33/128; Q4_0/Q8_0 K; head-major and
  token-major V. Query and output deliberately have different padded strides.
- 23 mapping rejections, checking that the destination metadata remains
  unchanged: disabled/reference/threaded calls, operator/precision/source/type
  mismatch, signed-dimension overflow, batching/Prefill, mask and block-stride
  mistakes.
- 13 cases that map successfully but must be rejected by the shared selector:
  inaccessible extents, aliases, unsupported features/capabilities, non-prefix
  mask, padded K row and signaling-NaN scale. No output bytes are modified.
- The actual header compiles as C++17 for GGML callers. Both host GCC and Clang
  ASan/UBSan run the same C matrix. GGML headers are hashed before and after the
  test to detect concurrent external-tree changes.
- Both unchanged real Qwen captures also pass mapping and shared admission,
  under GCC and Clang ASan/UBSan: D128, 12 Query heads, two KV heads, capacity
  256 and visible prefix 128. Input shapes/strides and bytes are checked against
  the original receipts before and after each run. Output metadata is constructed
  from GGML's `FLASH_ATTN_EXT` constructor contract `[D,Hq,1,1]`; it is not claimed
  to be a tensor object dumped from the running model. All output bytes remain
  untouched. These tests use the reference capability initializer, not hardware.

The five Python tests cover the C++ header, GCC and sanitizer matrices, and GCC
and sanitizer real-capture mapping. `ggml_decode_capture.c` shares the metadata
fixture rather than maintaining a second tensor-layout definition.

Run from `verification/akv/quantized_kv`:

```sh
python3 -B -m unittest test_ggml_decode -v
```

These are host mapping/admission tests, not VCS coverage or model performance.
