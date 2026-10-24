# Actual RVV Query / QBS score numerical inquiry

Sealed build: `verification/out/akv-quantkv-rvv-qbs-build-20261024-01`.
Its independent run `verification/out/akv-quantkv-rvv-qbs-20261024-01` is PASS:
raw log, host replay, actual work and UVM were independently rechecked. All16
scores and flags match original RVV, QBS hardware and both reference executions.
Receipt: `verification/akv/results/quantized-kv-qk-numeric-20261024.json`.

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
baseline dot's flags. The offline checker `check_rvv_qbs.py` replays exported
bytes through `host_score.c`, linked against the unmodified QBS reference and
host libm. This supplies an independent FP implementation of the same QBS
arithmetic specification, not an independent GGML quantizer. It checks all
16 scores and flags, Query/score order, finite outputs, reported baseline
differences, suite completion and UVM severity summaries. Actual QBS work,
image identity and UVM transactions still need the bounded execution worker;
transcript acceptance alone is not RTL acceptance.

Host sanity/rejection tests:

```sh
python3 -B verification/akv/quantized_kv/test_rvv_qbs_check.py
```

Three numerical-checker tests pass: exact known Q8_0/Q4_0 dot products and zero
activations; explicit baseline-difference reporting; and rejection of fourteen
transcript mutations plus changed K operands. These synthetic checker tests
are not additional real-model RTL coverage. The executed
sixteen-score inquiry is accepted separately by its run receipt above.

## Bounded native execution

`run_rvv_qbs.py` consumes the sealed build without rebuilding RTL or ELF. It
rechecks source/capture/artifact hashes, the accepted image and source manifest,
then builds the independent host oracle. Each score must follow exactly one
successful QBS command. The 16 commands must read 4096 logical payload bytes:
16 descriptors, four Q8_0 Query blocks per command, and four unchanged K blocks.
Each command has nine logical read ranges; AXI burst counts may exceed nine
because alignment can split a range. DIRECT must not report context reuse.
The expected total is not inferred from successful software return values.

After simulation exits normally, the worker requires independent UVM backend,
AXI read and write checks, checks their exact log/trace/ELF/image identities,
and rechecks all pins. An inquiry PASS means host QBS arithmetic, hardware and
protocol agree; it does not require original RVV and QBS bit equivalence and
does not approve deploying the quantized Attention path.

```sh
python3 -B -m unittest discover -s verification/akv/quantized_kv \
  -p 'test_rvv_qbs*.py' -v
python3 -B verification/akv/quantized_kv/run_rvv_qbs.py \
  --build verification/out/akv-quantkv-rvv-qbs-build-20261024-01 \
  --output <FRESH_OUTPUT_DIRECTORY> --preflight-only
```

Five host tests pass, including twelve work-record mutation rejections and
worker fail-closed checks. For execution omit `--preflight-only` and let a
direct-owned transient service run the worker; the default hard bound is three
hours. Never reuse an existing output directory or edit pinned helpers while
the worker is consuming them. No Verilator, URG or synthesis is involved.

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

## Multioutput follow-up

`batch_qk_main.c` and `build_batch_qk.py` prepare a separate ELF with all12
real Query heads from both captures, not duplicated heads0/6. Each profile
computes the complete12x128 score matrix with M4+M2/N32 DIRECT calls; extra
M2/N31 and M4/N1 calls check token62/64 boundaries without reading hidden
cache rows. Total:40 commands,3336 outputs and24 actual Query exports.
Independent geometry tests verify complete coordinate coverage, head
ownership, valid weight alignment and absence of hidden-row reads.

Build: `verification/out/akv-quantkv-batch-qk-build-20261024-01` is
`BUILT_NOT_EXECUTED`. Only the new main is compiled; original primitive,
startup, runtime and real-data objects are reused after checking sealed hashes.
No on-target scalar score reference is linked: acceptance must replay exported
Query/score bytes with the independent host oracle. The old sixteen-score PASS
does not accept this multioutput ELF. A strict batch transcript/work checker
and bounded worker are still required before launch.
