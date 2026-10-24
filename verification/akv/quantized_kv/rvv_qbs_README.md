# Actual RVV Query / QBS score numerical inquiry

Prepared build: `verification/out/akv-quantkv-rvv-qbs-build-20261024-01`,
`BUILT_NOT_EXECUTED`. No simulator or numerical acceptance yet.

## Exact code and real operands

The linked object is the untouched current complete GGML RVV `quants.c` TU,
not extracted functions or a replacement quantizer. Its explicit compiler
contract is recorded by `build_rvv_primitives.py`. The new main calls actual
`quantize_row_q8_0`, `ggml_vec_dot_q8_0_q8_0` and `ggml_vec_dot_q4_0_q8_0`.

Each of the two fresh real host captures contributes its own F32 Query and
unchanged quantized K. Select Query heads0 and6, corresponding to KV heads0
and1, and visible tokens0/63/64/127. The two cache configurations are K=Q8_0 /
V=Q8_0 and K=Q4_0 / V=Q8_0. The V calculation is not executed by this test.
All selected positions are visible in the actual128-token prefix. No masked
or uninitialized future row is evaluated.

For D128, each Query encodes four Q8_0 blocks =136 bytes. Four exports record
the actual target quantizer output, FCSR and VCSR. No host quantizer is used
as a byte-equivalent substitute. Each score calls QBS M1/N1/Kblocks4 DIRECT
against the original K row: Q8_0 stride136B, Q4_0 stride72B, head capacity256.
Actual ABI alignment is2B for weights and4B for activations, so these row bases
are legal without copying. This is16 commands, not a throughput experiment.

## Separate numerical questions

1. Hardware versus QBS contract: original `verification/qbs/qbs_ref.c`
   executes the identical descriptor and exact target-produced Query bytes.
   Each hardware result and fflags must match. Its arithmetic is not changed.
   Only calloc/free names are remapped at compile time to a bounded128-byte
   fixture for its one M1 destination allocation; no bare-metal heap is needed.
2. QBS versus original RVV: raw score bits and flags are printed separately.
   Differences are counted by format, not hidden by changing tolerances. Q4_0
   has a proven different scale-rounding order; even a consistent difference is
   not deployment approval. Q8_0's compiled order is promising but not assumed
   numerically accepted before execution.

Initial FRM=RNE and VCSR5 are set independently for quantization, original dot
and QBS. Drained snapshots precede comparison. Output/activation guards,
inactive destination memory, allocator bounds/ownership and finite scores are
checked. The original reference's flags are recorded independently of the
baseline dot's flags. Future offline checking should additionally replay the
exported bytes through a host reference; an on-chip scalar reference shares
the target FP resources and is not alone a fully independent FP implementation.

## Reproduce preparation

```sh
python3 -B verification/akv/quantized_kv/build_rvv_qbs.py \
  --output <FRESH_BUILD_DIRECTORY>
```

The builder rechecks original capture/build/source identities, exact primitive
object, source dependencies, accepted image, reference/ABI headers, libm/libgcc,
real linked symbols and ELF bounds. No original capture or runtime source is
modified. A reviewed strict transcript/work checker plus independent UVM and
bounded worker are required before execution and acceptance. It does not yet
prove complete quantized-KV Attention, quantized-V PV, runtime selection, model
quality or speedup.
