# Parallel Q8_K M4 activation group sums

## Motivation and invariant

The current packed M4 producer in llama.cpp computes the signed-byte sum of
each 16-element group separately: slide, widening reduction, vector-to-scalar
extraction, scalar store. For a 256-element block and four rows this requires
64 scalar-result reductions. These sums are part of the activation payload;
they are not optional statistics.

The candidate sign-extends the quantized vector to i16, then applies slide/add
stages with offsets 8,4,2,1. Positions 0,16,... each contain precisely their
original 16-element sum. A gather selects those positions and a strided i16
store writes one row's sums at byte stride 8, preserving the existing x4 layout.

The proof relies on integer range, not approximate floating-point associativity:
each signed-byte group sum lies in [-2048,2032], and every partial sum fits i16.
No saturating operation, quantization, FP rounding or scale calculation changes.
Unselected positions may span group boundaries; only group starts are stored.
The internal leaf requires positive vl divisible by 16, fitting e8m1 VLMAX,
and a disjoint destination with the required interleaved writable extent.

## Functional evidence

`verification/out/m4-vector-group-sums-reference-20261029-01` is PASS:

| VLEN | Tested vl | Input cases | Interleaved row positions per case |
| ---: | --- | ---: | ---: |
| 1024 | 16,32,64,128 | 256 | 4 |
| 256 | 16,32 | 128 | 4 |

Cases include all -128, all +127, alternating extrema, and deterministic mixed
bytes. Checks compare every destination and guard word against scalar sums,
and require unchanged FCSR/VCSR. QEMU is functional-only evidence.

ELF SHA256:
`a2e94efb3cc4b75581aa5fda8be4fda2d42ca4ff0ea9f48f8d318d070593d637`.

Reproduce in a fresh directory:

```sh
python3 -B verification/akv/quantized_kv/register_pv/run_online.py \
  --group-sums --fp-contract fast --execute-reviewed \
  --output verification/out/m4-vector-group-sums-reference-new
```

## Remaining gates

Complete quantizer comparison also passed in
`verification/out/m4-vector-sums-quantizer-reference-20261029-01`, at VLEN1024
and VLEN256. Each run has 57 comparisons: nine real-data checks (three M4
groups with three initial sticky flag states), plus 48 checks spanning K=256,
512,1536,6144 and zero, alternating-sign and deterministic mixed-value inputs.
All packed output bytes, guard bytes, input bytes, FCSR and VCSR match the
existing RVV packed quantizer. The test requires actual vector-path execution.

Real input is the first 12 of 15 captured Qwen2.5-1.5B projection activation
rows, K=1536, from `blk_0_attn_q_weight/activation_f32.bin`. The entire 92160-byte
capture is checked against the earlier accepted projection manifest before
loading. The final three rows are not tested as an M4 group. This comparison
uses the existing quantizer as the oracle; the independent integer scalar
oracle belongs to the earlier group-sum leaf tests.

Complete-test ELF SHA256:
`b7d66d04d0605d9647b2104d9153f9fc571bb2d9d4c40efb3bf1098ffe7c49a2`.
`test_source_identity.py` verifies that the experimental full quantizer differs
only in namespace/include plumbing and its group-sum body. Quantization,
signed-maximum selection, scales, rounding and fallback remain identical.

## Preparation-only RTL acceptance

`verification/out/m4-group-sums-native-vcs-20261029-01` completed PASS, with
independent protocol checks, unchanged source/image pins and separate replay.
Both paths execute the complete packed M4 quantizer on the same real 4x1536
activation and compare all 7008 output bytes to the accepted packed golden.
The timed region includes domain checking, signed maximum/scales, encoding,
group sums and packed output stores, but not verification/printing.

| Path | ABBA trial cycles | Mean |
| --- | --- | ---: |
| Current packed producer | 76177, 75943 | 76060 |
| Parallel group sums | 44586, 44300 | 44443 |

Speedup is 1.7114056x and cycle reduction 41.5685%. Both paths actually took
their vector branch. All trials have identical FCSR=9 and VCSR=5; byte/guard
checks pass. This is a preparation measurement, not QBS execution, a complete
projection, or a whole model. The measurement uses the existing canonical
VLEN1024 RTL image and does not modify hardware.

- ELF SHA256: `efd6a1229ee1e48ea8365608aa148863d195839ecd5a63649eb112a7e7b7a943`.
- Result SHA256: `b2c62d2636c232f0473a5cebae65891298fbd225f51e078e392b8bb92262d5e4`.
- Log SHA256: `48ae00e9252c1ed57403eedeb2526710f470d3cfd374a2efe1d3d9577942050b`.
- Independent replay verified 981 sealed inputs and reran the log/golden checker.

## Remaining gates

The measured preparation gain justifies the longer complete-projection gate.
Use exact-byte prepared-activation reuse in both paths, comparing only the
cold producer, so the existing cache optimization is not counted again.
Keep Q/V/K outputs, profiles, command counts, order, CSR and input checks.
Do not compare against the old repeated-quantization baseline or multiply
separately measured ratios. The candidate is not yet integrated into llama.cpp.
Instruction reduction alone is insufficient: strided-store cost, register
pressure and generated spills can offset the eliminated scalar reductions.
Do not substitute a synthetic standalone reduction ratio for model or full
projection speedup. Preserve the current quantizer until these gates pass.
