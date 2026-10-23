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
