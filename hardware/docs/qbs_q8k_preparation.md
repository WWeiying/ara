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
This first preparation run completed PASS. Its generic observations are
267361/267230 cycles and candidate observations are 248034/247885 cycles.
ABBA sums are 534591/495919, a 1.07798x preparation speedup (7.234% fewer
cycles). All prepared bytes and status checks pass; UVM reports 10764 matched
requests/responses, zero exceptions/protocol errors and 12288 matched backend
allocations/completions. The independent auditor also binds the executed ELF,
image libraries, raw log and trace to the saved evidence. Its receipt is
`verification/qbs/results/q8k-prepare-soc-20261023.json`.
A passing preparation measurement must still be followed by a complete
projection test and actual GGML dispatch validation; no full-projection speedup
is inferred from it.

The full-projection data gate is prepared separately by
`prepare_q8k_projection_data.py`: real M4/N1536/K1536 attention-Q weights,
the same first four captured activation rows and the independent production
Q8_K bytes. The output reference decodes original row-major Q4_K weights and
M4 Q8_K bytes, then computes 6144 outputs with FP64 products and `math.fsum`.
This calculation does not use the R4 packed weight blob, QBS reference engine
or vector candidate to obtain expected results. Q8_K bsums are independently
validated before projection. The R4 weight blob is produced only for the DUT.

The prepared data in
`verification/out/qbs-q8k-projection-data-20261023-01/` passes captured-GGML
cross-checking at unchanged 2e-3 absolute/relative tolerance; maximum absolute
drift is 1.3857520642091004e-6. The tighter planned DUT oracle tolerance remains
2e-4 absolute plus 2e-5 relative. This is data/oracle preparation, not a passed
RTL projection measurement or a model-level numerical result.

### Full-projection paired measurement

`q8k_projection_soc.cpp` uses one ELF and one shared output buffer for four
trials in generic/vector/vector/generic order. Both preparation paths consume
the same F32 rows and produce the same M4 Q8_K layout. After preparation, both
call the unchanged production `qbs_native_execute_command` entry for 48 tiles
of N=32. Descriptor construction, command fences/configuration, execution and
output stores remain inside the matrix phase. Offline weight repacking is
excluded equally. Domain preflight, maximum selection, quantization and bsums
are inside the preparation phase; no quantization is precomputed for timing.

Every trial independently checks all 7008 prepared bytes and all 6144 output
values, output canaries and FP/vector status. All four output bit checksums
must also match each other. The acceptance parser requires positive phase
cycles and exact `total = preparation + matrix` accounting. The trace audit
requires 192 unique M4 QBS allocations and 512 result bytes per command,
98304 bytes overall. The UVM interface audit must pass separately.

The first paired run is scheduled under
`qbs-q8k-projection-soc-20261023-01.service`, with private outputs in
`verification/out/qbs-q8k-projection-soc-20261023-01/`. The reused image is
4-lane/VLEN1024 with 16 MiB simulation RAM and unchanged AXI-delay configuration.
The simulation bound is three hours. This run is separate from the preparation
microbenchmark, not a continuation of its timing interval. Do not add their
cycles or compare them as if code layout and cache state were identical.
Report the paired projection's own phase cycles and full interval; a result
remains pending until raw output, trace, UVM and source pins all pass.

### Measured preflight bottleneck and successor gate

Before the first ABBA run finished, its existing scalar retirement trace
already contained the first two complete timed intervals. These observations
are diagnostic only, not accepted performance results: generic 267361 cycles,
candidate 248034 cycles. They are the values read by the ELF's `rdcycle` PCs
`0x800003ba` and `0x800003e6`, not estimates from QEMU wall time.
The candidate entry at `0x80000104` retires at cycle 365282; its first
post-preflight instruction at `0x800001ce` retires at cycle 450475. That
85193-cycle interval is 34.35% of this candidate call. The six scalar
maximum/scale intervals from `0x80000228` to `0x8000028a` sum to 73900 cycles.
These are instruction-retirement boundary intervals, not a disjoint execution
unit utilization or stall attribution. The remaining ABBA observations and
independent byte/CSR checks are still required.

The isolated successor `q8k_m4_domain_vla.h` targets the measured first cost
without changing the quantizer. For each four-row block, it loads FP32 bits,
clears the sign and accumulates unsigned maximum and minimum of `abs_bits-1`
using RVV integer operations. Zero wraps to UINT32_MAX, while exactly the
nonzero subnormal range maps below 0x007fffff. The maximum-domain upper bound
also excludes infinities and NaNs. Thus the original rejection conditions can
be evaluated using two reductions per row instead of scalar per-element tests.
The original lower/upper maximum bounds remain unchanged.

Partial chunks preserve inactive accumulator elements with tail-undisturbed
max/min updates. Reductions use the initial span, not the last short VL.
This is necessary for non-divisor caps such as 7. The helper does not perform
FP arithmetic, CSR save/restore or saturating fixed-point operations. The
caller retains responsibility for nonnegative, block-aligned K, as in the
existing candidate contract.

Caps 1/7/16/32/64/256 compile with the target GNU RV64GCV toolchain.
`run_q8k_domain_native.py` independently compares classification with the
original scalar rule using 134 datasets, all five rounding modes, three initial
FCSR/VCSR pairs and all six caps at VLEN128/1024 (12060 checks per VLEN).
The datasets include invalid values at early, chunk-boundary and late positions,
all-zero blocks, numerical-domain boundaries and six real capture slices.
Execution completed PASS: 24120 comparisons, unchanged FCSR/VCSR and input,
with matching cross-VLEN digest `a7f5327813608389`. Raw logs were independently
rechecked; the receipt is
`verification/qbs/results/q8k-domain-native-20261023.json`.
This is not yet a full quantizer or RTL performance result. The sealed candidate
and both running VCS tests are unchanged; integrate only after this gate passes
and the current consumers have finished.

The isolated full-quantizer successor is
`ggml_q8k_m4_prepare_vla_candidate.h`. Its quantize template is checked to be
text-identical to the sealed candidate's template; only its `vector_domain`
helper redirects to the accepted integer VLA preflight. This temporarily
preserves the earlier candidate for its still-running consumers. It does not
introduce a different scale selection, FMA rounding or bsums algorithm.

`build_q8k_vla_native.py` redirects only the include and three candidate calls
in the original native harness. The same production generic archive, 50-case
matrix, expected paths, byte comparisons, CSR checks and parser are reused.
The original harness and sealed sources are not edited. The successor native
worker `qbs-q8k-vla-native-20261023-01.service` completed PASS: 12000 full
quantizer comparisons at VLEN128/1024. Independent raw-log checks also confirm
that all per-case output digests match the original candidate. The receipt is
`verification/qbs/results/q8k-vla-native-20261023.json`. This closes the
isolated full-quantizer numerical gate, not its RTL performance or actual
production-TU integration gate.

For subsequent RTL measurement, `build_q8k_vla_soc.py` first creates a fresh
private baseline build using the unchanged preparation or projection builder.
It recompiles only the benchmark translation unit with the candidate include
and namespace redirected, then relinks with those freshly produced common and
oracle objects. Unique-argument checks prevent accidental substitutions in
compiler/linker commands. The full original source manifests, build artifacts,
new helper and ELF are pinned. This reuses the existing ABBA emitters and
acceptance parsers without changing ongoing builds or writing over their ELFs.

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
