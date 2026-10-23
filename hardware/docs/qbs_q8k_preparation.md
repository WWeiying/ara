# Q8_K M4 preparation: numerical contract and implementation gate

Status: isolated software candidate, not enabled in production. No RTL change.
The broader activation-preparation objective includes both Q8_0 and Q8_K;
the accepted Q8_0 results do not establish this candidate's correctness or speed.

## Actual consumer and reference

The QBS M4 K-quant path in llama.cpp uses the specialization
`ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>` in `ggml-cpu/repack.cpp`, which calls
`ggml_quantize_mat_q8_K_4x1_ara_generic`. This function, not the single-row
RISC-V quantizer, is the immediate byte and floating-point-status reference.

For each 256-element block and each of four input rows:

1. Select the first value attaining the largest absolute magnitude. The
   comparison is strict; equal positive/negative maxima retain input order.
2. Compute `iscale = -127 / signed_max` and `d = 1 / iscale`. All-zero blocks
   use zero scales. Preserve the actual M4 reference's zero behavior.
3. Multiply each source by its row scale, then round using the reference's
   binary32 addition of 12582912 and extraction of the fraction bits.
4. Write bytes with `qs[element * 4 + row]` ordering.
5. Sum each consecutive group of 16 signed bytes and write
   `bsums[group * 4 + row]`. These sums are consumed by asymmetric profiles;
   correct dot output for one symmetric format is not sufficient validation.

The upstream single-row RVV code selects between separate min/max reductions
and uses explicit RNE conversion. It is not a byte-equivalent replacement for
the M4 reference on signed equal-magnitude ties. This observation does not
by itself establish a model correctness bug in that separate implementation.

## Candidate

`verification/qbs/ggml_q8k_m4_prepare_candidate.h` preserves scalar scale and
maximum selection, then uses RVV multiply, bias-add, bit extraction,
nonsaturating integer narrowing, strided output stores and widening integer
reductions. A compiler barrier prevents multiply/add contraction. Unlike the
Q8_0 roundf candidate, it does not clear conversion flags: no FP-to-integer
conversion is introduced, and the reference's bias-add can itself set NX.

The first version works within 16-element sum groups. AVL caps 1, 7 and 16
exercise strip mining, including splits inside a sum group. This is a
correctness-oriented candidate geometry, not a claim of optimal VLEN1024
utilization. Wider quantization with separate grouped summation must be
evaluated only after the exact numerical gate passes.

Integer-only preflight rejects nonfinite/subnormal inputs and conservatively
bounds nonzero maxima to [2^-110, 2^111]. Non-RNE rounding, zero-length input
and rejected domains call the actual generic function before output writes.
No shared mutable scratch or global mode changes are introduced. Input/output
non-aliasing and four complete rows remain the production preconditions.

## Acceptance

- Compile all AVL caps with the target RV64GCV compiler and strict FP options.
  This gate passed on 2026-10-23; it is not an execution result.
- Compare all packed bytes, scales and bsums against the linked production
  generic, with output guards and immutable source checks.
- Cover real captured K-quant projection inputs, multiple blocks, opposite
  signed maxima in both orders, half-integer boundaries, zeros, extreme
  scales, rejected inputs and the complete rounding/sticky-flag matrix.
- Execute VLEN128 and VLEN1024, caps 1/7/16; compare FCSR and VCSR. A separately
  compiled helper gate does not substitute for production-TU checks.
- After numerical acceptance, measure preparation and full projection with
  the same RTL, real input, layout and output oracle. Include preflight cost.
- Only then integrate a shared helper behind opt-in selection in GGML and
  test actual graph dispatch. Do not claim production or model acceleration
  from an isolated helper or a QEMU wall-clock measurement.
