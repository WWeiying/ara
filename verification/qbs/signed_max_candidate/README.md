# Private signed absolute-maximum candidate

The accepted Q8_K M4 quantizer still uses a scalar loop to choose each block's
largest magnitude, retaining the sign of the first occurrence. This candidate
changes that selection only; it is not installed in the quantizer or runtime.

For finite binary32 inputs, unsigned ordering of sign-cleared IEEE bits matches
magnitude ordering. The helper reduces those bits with RVV integer operations,
then searches chunks in source order with `vfirst` to retain the first tie's
sign. All-zero blocks return positive zero, matching the original strict `>`
loop. Tail-undisturbed maxima preserve earlier chunks when the last VL shrinks.

Preconditions: finite input, valid count-sized input storage, and a valid
`absolute` output that does not overlap input. The production quantizer's
existing full-input domain preflight must remain in place; this helper is not
a replacement for NaN, infinity, subnormal, scaling-range or rounding-mode
admission. No FP arithmetic is used for selection.

The second scan adds loads, so fewer scalar instructions do not prove speedup.
Full quantization and complete projection timing are required before adoption.

## Completed gate

`run.py` builds a static GNU RVV program and runs the same ELF with VLEN 256 and
1024. Each run compares 1315 datasets across five rounding modes, four incoming
fflags combinations and all eight vcsr values: 210400 checks per VLEN.
Lengths include 0, 1, 15/16/17, 31/32/33, 127/128/129, and 255/256/257.
Each possible maximum position and an opposite-sign adjacent tie are covered,
along with signed zeros and finite exponent extremes. The reference is the
original scalar floating-point loop with automatic vectorization disabled.

Both runs passed in `verification/out/q8k-signed-max-reference-20261026-01`.
QEMU verifies functionality only; no cycle comparison or whole-quantizer
acceptance is implied. Next gates are complete quantized bytes/scales/bsums and
CSR against the actual production generic on real captured activations,
followed by one bounded paired current-RTL projection measurement if warranted.
