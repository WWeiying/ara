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

The candidate is not integrated into llama.cpp or the QBS RTL. Next compare
the complete packed Q8_K activation bytes, scales, sums and FP flags using real
model activations, then measure the entire preparation/projection call on VCS.
Instruction reduction alone is insufficient: strided-store cost, register
pressure and generated spills can offset the eliminated scalar reductions.
Do not substitute a synthetic standalone reduction ratio for model or full
projection speedup. Preserve the current quantizer until these gates pass.
