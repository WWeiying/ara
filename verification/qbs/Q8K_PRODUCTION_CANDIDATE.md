# Q8_K shared-runtime selection gate

## Purpose

The isolated Q8_K helper already passes numerical acceptance and an RTL
preparation measurement. Those results do not prove that GGML's actual
`ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>` entry selects or compiles it correctly.
This gate checks that next boundary without modifying sources pinned by the
running full-projection experiments.

`build_q8k_production_candidate.py` copies the complete current `repack.cpp`
into a new output directory. Only that private source gains the candidate
include, a test-only selection observer and selection in the Q8_K
specialization. The existing generic function body is not rewritten. This is
an opt-in candidate for the existing QBS/no-Zvfh build, not a portable upstream
patch or a change to live llama.cpp. The live runtime remains unchanged.

## Compilation and independent calls

The full private translation unit uses the exact sealed production compile
command: GNU RV64GCV, `-O3`, `-DNDEBUG`, ordinary production auto-vectorization,
and no fast-math or LTO. Only input/output paths change. The separate test
translation unit does not include or instantiate the candidate helper. Its
undefined production specialization reference is checked with GNU `nm`.
The linked specialization must contain the candidate's RVV load, fused
multiply-add and strided-byte-store instructions plus its generic fallback.
GNU O3 may inline the helper, so a retained helper symbol is not required.
The unchanged generic function in that same object is the oracle.

Selection uses the existing `GGML_RISCV_QBS_M4_PREPARE=1` opt-in in this private
candidate. A test-only observer reports whether the helper selected RVV or its
generic fallback. No custom QBS instruction executes in this quantization-only
test; QEMU provides functional ISA semantics, not RTL cycles.

## Numerical scope

The original 50-dataset acceptance harness is reused, including six genuine
activation captures, zero and signed-zero cases, signed maximum ties, affine
block sums, the fused-rounding witness, subnormal/nonfinite rejection, long K,
five rounding modes and eight initial FP/vector-status settings. Every packed
byte, FP scale, block sum, FCSR/VCSR, input immutability and output guard must
match the linked generic oracle.

There is one production helper configuration, MaxAVL=16. The old harness's
three cap slots are deliberately mapped to three repeat observations of that
same production entry. Thus the 6000 comparisons per VLEN represent 2000
distinct case/environment combinations repeated three times, **not** three
production AVL modes. VLEN128 and VLEN1024 must have identical result digests.
The previously accepted isolated-helper gate, not this gate, covers caps1/7/16.

## Reproduction

```bash
python3 verification/qbs/build_q8k_production_candidate.py \
  --native-build verification/out/qbs-q8k-m4-native-build-20261023-01 \
  --native-run verification/out/qbs-q8k-m4-native-20261023-01 \
  --production-build verification/out/qbs-m4-production-csr-build-20261023-02 \
  --output /absolute/new/build

python3 verification/qbs/run_q8k_m4_native.py \
  --build /absolute/new/build \
  --configuration /absolute/native-qemu-configuration.json \
  --output /absolute/new/run
```

The builder requires production archives from the accepted native manifest;
the similarly named earlier production build is rejected before compilation.
Running sources, ELFs and simulator images are not overwritten. Acceptance
does not enable the candidate in live GGML, establish graph/model dispatch,
or substitute for the pending full-projection RTL performance gate.

## Accepted full-TU numerical result

The private production entry passed both VLENs. Independent raw-log rechecking
accepts 12000 observations (4000 distinct case/environment/VLEN combinations,
each repeated three times), matching the isolated successor's per-case output
digests. The receipt is `results/q8k-production-candidate-native-20261023.json`.
The first build retained a missing test-side template declaration; the second
retained a rejected symbol-presence test despite correct O3 inlining. Neither
was executed or counted as an RTL failure. Build03 is the accepted input.

## Actual GGML graph selection

`build_q8k_graphs.py` consumes the accepted build and creates a separate private
full TU with a thread-local path observer and one Q8_K preparation trace line
per call. The observer is test-only, not hidden hardware state or a new runtime
requirement. The quantizer body and generic oracle remain unchanged. The graph
caller reuses `ggml_m4_prepare_production/graph.cpp`, its independent scalar
oracle and sixteen shapes; this suite uses deterministic graph inputs, not a
new model capture. Real activation datasets are covered by the numerical gate.

`q8k_graph_init.c` executes preparation OFF/ON with six existing context, wide-M
and thread settings per mode. `check_q8k_graphs.py` requires 384 complete graphs,
exact paired output digests and 52 actual Q8_K M4 preparation calls per mode.
It retains the old checker's Q8_0 preparation, native-command, lifetime and
fallback checks rather than replacing them with new PASS strings. Wide-M and
M1/M2/M3 paths must not report an M4 call. The three-thread cases exercise the
existing GGML scheduler under one guest hart. This checks concurrency and
selection semantics, not physical parallel throughput.

```bash
python3 verification/qbs/build_q8k_graphs.py \
  --accepted-run verification/out/qbs-q8k-production-candidate-native-20261023-01 \
  --production-build verification/out/qbs-m4-production-csr-build-20261023-02 \
  --output /absolute/new/graph-build

python3 verification/qbs/run_q8k_graphs.py \
  --build /absolute/new/graph-build \
  --configuration verification/out/qbs-m4-production-native-20261023-01/configuration.json \
  --output /absolute/new/graph-run
```

No existing worker, helper, live runtime source, archive or ELF is overwritten.
The graph boot is bounded to 900 seconds. A passing result is functional QEMU
evidence only; full-projection RTL performance and eventual live runtime
integration remain separate requirements.

The graph worker completed PASS on 2026-10-23. Independent rechecking accepts
384 graphs and 74592 checked output words, with exact OFF/ON digests. Each mode
contains 52 Q8_K M4 preparation calls and 72 Q8_0 preparation calls. Context,
wide-M, tail and three-thread dispatch checks all pass. The receipt is
`results/q8k-production-graphs-20261023.json`. This closes the private graph
selection gate; the candidate has not been enabled in live llama.cpp.

## Full-projection RTL result

The original (pre-VLA-preflight) quantizer completed the full real M4/N1536/
K1536 Q projection on 2026-10-23. One ELF executes generic/vector/vector/generic
trials, with 6144 outputs per call checked against the independent reference.
All four checksums are `fbb83bb6df5ca009`, with identical FP status. The trace
contains 192 accepted QBS commands and 98304 result bytes across four calls.

| Phase, sum of two matched trials | Generic | Vector candidate |
| --- | ---: | ---: |
| Activation preparation | 534360 | 496054 |
| QBS matrix execution | 685356 | 685155 |
| Complete projection | 1219716 | 1181209 |

The full-projection speedup is 1.032600x; this is not a model-level speedup.
The receipt is `results/q8k-full-projection-original-20261023.json`. The VLA
preflight successor has a separate still-running full-projection gate and is
the implementation used by the private production/graph functional gates.
Do not attribute the original candidate's full-projection result to that
successor or combine preparation-only speedups with complete-projection data.
Live runtime deployment remains opt-in and pending its matching RTL result.
