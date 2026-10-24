# Finite Q8_0 V Decoding Inquiry

## Purpose And Unchanged Contract

The frozen production `ggml-quants.c` object decodes Q8_0 V with scalar
integer-to-float conversions and multiplications in this GNU configuration.
The shared-head Attention candidate already avoids decoding the same V row for
every Query head. This inquiry isolates whether standard RVV decoding is also
worth using; it does not conflate that question with QBS or PV scheduling.

Candidate source:
`software/akv/experimental/quantized_kv/q8_0_value.h`.
Each original 34-byte block still contains a two-byte F16 scale and 32 signed
eight-bit values. The candidate performs:

```text
Original bytes -> signed-eight-bit load -> sign extend to 32 bits
               -> exact integer-to-F32 conversion -> F32 scale multiply
               -> same F32 output row
```

The load uses `e8,mf2`, sign extension produces `e32,m2`, and a dynamic VL loop
handles the remaining elements of each 32-element block. There is no hardcoded
VL=32 assumption inside the kernel, no new instruction, no QBS command and no
change to Query quantization, score order, online Softmax or PV accumulation.
The caller must supply already-admitted, finite-scale, disjoint valid buffers.
Nonfinite scales are outside this candidate domain and retain ordinary fallback.

Finite F16 has at most 11 significant bits; multiplying by an eight-bit integer
needs fewer than the 24 significant bits of F32. Conversion and multiplication
are exact, including signed zero, and the finite product range fits F32 without
underflow or overflow. Thus this inquiry requires bit-exact original/candidate
outputs and zero new floating-point flags, not an approximate tolerance.

## Actual Experiment

- Two unchanged real Qwen2.5 capture V tensors: K=Q8_0/V=Q8_0 and
  K=Q4_0/V=Q8_0. Their V bytes are independently fixed by the original receipts.
- Each trial covers both KV heads, all 128 visible tokens, D128, and 32,768
  output values. Stored but masked capacity rows 128--255 are not read.
- ABBA per capture: original scalar decoder, RVV candidate, RVV candidate,
  original scalar decoder. Eight trials total; row traversal and call counts
  are the same. Time includes the decoding loop and result stores/drain, but
  not guard setup, numerical comparisons, hashing or UART output.
- A directed prelude covers 14 positive/negative zero, subnormal, normal and
  maximum finite F16 scales crossed with every signed-eight-bit value: 3,584
  outputs. Any mismatch prints its first scale, integer batch, element index,
  expected/actual bits, or exception flags before the failure is reported.
- Native target code compares every candidate output word with the original
  production decoder. Both outer guards, repeated outputs, FCSR and VCSR are
  checked. No on-target QBS reference or unrelated accelerator work is linked.

The independent host oracle reads original byte offsets, decodes each finite
F16 scale, multiplies by signed bytes, and hashes the exact little-endian F32
words. All eight target hashes must match. This is an independent full-output
hash check in addition to the target's word comparisons; it is not a host dump
of every output word or a per-instruction architectural-state comparison.

The worker additionally requires an actual zero simulator exit, complete raw
records, no failed assertions, independent UVM backend/AXI read/write checks,
and unchanged source/tool/image/data hashes before and after execution.
It records any slowdown rather than treating a positive speedup as a functional
pass condition. Three host checker/worker tests cover format arithmetic,
hidden-row omission, malformed/mutated transcripts and wrong build metadata.

## Artifacts And Promotion Gate

- Current build: `verification/out/akv-quantkv-value-decode-build-20261024-02`
- Run: `verification/out/akv-quantkv-value-decode-20261024-01`
- Worker: `run_value_decode.py`
- Checker: `check_value_decode.py`
- Service: `akv-quantkv-value-decode-20261024-01.service`

Build 01 preceded the added first-error diagnostics and is not the run input.
The frozen run has a three-hour execution bound and owns independent outputs.
The other QK and Attention workers do not consume this new candidate.

No production GGML source, existing F16 AKV runtime, RTL, ABI or default selection
has changed. A passed decoder inquiry proves only this finite decoding domain.
Promotion still needs a measured benefit in complete Attention with the same
real data and admission overhead, followed by shared-source GGML integration.
Other V encodings and unsupported feature/layout cases remain ordinary paths.
