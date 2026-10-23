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
3. Evaluate source times row scale plus 12582912, then extract fraction bits.
   The pinned production compiler contracts the multiply and addition into
   `fmadd.s`: the executable reference therefore rounds only once here.
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
maximum selection, then uses explicit RVV FMA with the bias constant, bit
extraction, nonsaturating integer narrowing, strided output stores and widening
integer reductions. Production disassembly, not source spelling alone, fixes
the contraction contract. Unlike the
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

On 2026-10-23, the native numerical gate passed 12000 comparisons across
VLEN128/1024: 50 datasets per VLEN, including six real activation captures,
five rounding modes, eight initial status settings and three AVL caps.
Each VLEN includes 936 candidate-path and 5064 fallback comparisons. Packed
bytes, scales, bsums, FCSR/VCSR, guards and input immutability match the linked
production generic; per-case digests match across VLENs. See
`verification/qbs/results/q8k-m4-native-20261023.json`. Production integration
and same-image RTL preparation/projection performance remain unproven.

### RTL preparation measurement in progress

The independent Linux production function exported the first four real
attention-projection activation rows, M=4/K=1536, into a 7008-byte Q8_K M4
reference. The exporter completed with FCSR=1 and unchanged VCSR=5. Its record
is `verification/out/qbs-q8k-oracle-20261023-01/golden.json`.

`build_q8k_prepare_soc.py` extracts the current production generic and its
`nearest_int` helper without manual algorithm substitution, checks that the
bare-metal reference still contains `fmadd.s`, and builds one ABBA executable.
Every call is checked against the independent reference, including scales and
bsums, output guards and FCSR/VCSR. The timed candidate includes its domain
preflight and scalar maximum search; setup, printing and comparison are outside
the interval. Both paths use the same output buffer and input capture.

The existing SoC image is executing this ELF under the direct systemd worker
`qbs-q8k-prepare-soc-20261023-01.service`, with a 7200-second simulation bound.
Results belong to `verification/out/qbs-q8k-prepare-soc-20261023-01/`.
Starting the simulator is not performance acceptance. A passing preparation
measurement must still be followed by a complete projection test and actual
GGML dispatch validation; no full-projection speedup is inferred from it.

- Compile all AVL caps with the target RV64GCV compiler and strict FP options.
  This gate passed on 2026-10-23; it is not an execution result.
- Compare all packed bytes, scales and bsums against the linked production
  generic, with output guards and immutable source checks.
- Cover real captured K-quant projection inputs, multiple blocks, opposite
  signed maxima in both orders, half-integer boundaries, zeros, extreme
  scales, rejected inputs and the complete rounding/sticky-flag matrix.
- Execute VLEN128 and VLEN1024, caps 1/7/16; compare FCSR and VCSR. A separately
   compiled helper gate does not substitute for production-TU checks. Include
   signed maximum bits `0x3f800001` and source bits `0xbda952a7`: the production
   FMA quantizes to 11 whereas separated multiply/add quantizes to 10. Reject
   a changed production contraction policy instead of silently assuming both
   forms have identical bytes or floating-point flags.
- After numerical acceptance, measure preparation and full projection with
  the same RTL, real input, layout and output oracle. Include preflight cost.
- Only then integrate a shared helper behind opt-in selection in GGML and
  test actual graph dispatch. Do not claim production or model acceleration
  from an isolated helper or a QEMU wall-clock measurement.
