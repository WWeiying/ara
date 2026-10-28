# Packed preparation: shape and numerical acceptance

This extends the accepted real-input prototype without changing its producer,
the live runtime, or RTL. All input/output objects used by the ongoing complete
Q/V/K timing worker remain unchanged.

## Comparison

`extent_test.cpp` compares three independently called implementations:

1. The production generic quantizer from the normal installed GGML archive.
2. The existing accepted M4 RVV producer.
3. The proposed packed-word producer.

The test compares every output byte, incoming/sticky FCSR behavior, VCSR,
output canaries, source integrity, and the fast-path/fallback decision. It uses
the production generic compiled by the existing normal library build, not a
new generic reimplementation or an assumed mathematical reference.

| Dimension | Tested values |
| --- | --- |
| VLEN | 128, 256, 512, 1024 |
| K | 0, 256, 512, 768, 1536, 3072, 6144, 8192 |
| Rows | Four contiguous rows |
| Output base | 64-byte aligned or offset by four bytes |
| Input base | Offset by one float from a 64-byte-aligned object |
| Floating-point rounding | RNE, RTZ, RDN, RUP, RMM |
| RNE incoming FFLAGS/VCSR | 0/0 and 17/7 |
| Other rounding incoming FFLAGS | 17 |

Twelve patterns cover the captured Qwen activation data, zero, opposite-sign
equal magnitudes, a final-element maximum, equal maxima across vector chunks,
signed zero, both admitted exponent boundaries, minimum normal values, and
finite cases that deliberately require fallback. Larger-K repetition of a
captured block is a shape test; it is not evidence from a larger real model.

NaN and infinity are outside the current generic quantizer's input contract.
Separate admission tests place quiet/signaling NaNs and infinities at seven
positions and verify rejection without changing FCSR/VCSR. They do not invoke
an undefined generic conversion or claim valid quantized outputs for NaNs.

## Result

`verification/out/m4-packed-extent-20261027-01/result.json`: **PASS**.

| VLEN | Exact byte/state comparisons | Nonfinite admission checks |
| ---: | ---: | ---: |
| 128 | 576 | 28 |
| 256 | 576 | 28 |
| 512 | 576 | 28 |
| 1024 | 576 | 28 |
| Total | 2304 | 112 |

Result SHA-256:
`f8ab0d9debce472ac360cd13a9c86179338496484a8dc16e5a389822cfa6aa82`.
All inherited and new source/library hashes were independently rechecked after
completion and matched. QEMU is used only for numerical and architectural-state
acceptance; none of these runs provides hardware performance measurements.

## Remaining production gates

- Complete-call VCS timing of the packed producer plus exact-input reuse is
  still independent of this result. Do not multiply isolated speedups.
- Both direct M4 dispatch and cache-miss production must use the same selected
  helper. Distinct producer identities must not share persistent cache entries.
- Preserve the existing aligned, nonoverlapping input/output contract and the
  little-endian guard. The alias-qualified packed stores are qualified for the
  tested GNU configuration, not for arbitrary compiler/LTO settings.
- Check actual runtime input strides before promotion. A cache admission
  rejection alone does not establish that the subsequent generic/direct
  quantizer accepts a padded-row view.
- Fresh normal GGML graph/model execution remains required after integration.
  This test neither enables the candidate by default nor changes ordinary RVV,
  QBS/AKV RTL, or numerical fallback rules.

Reproduce with a new output directory:

```sh
python3 verification/qbs/m4_prepared_reuse/packed/run_extent.py \
  --output verification/out/NEW_PACKED_EXTENT
```

The worker rejects drift of its accepted producer/library manifests, compiles
only the new driver, and reuses the already qualified producer objects and
normal libraries. It stops on any failing VLEN configuration.
