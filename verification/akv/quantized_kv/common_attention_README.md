# Complete Attention Through The Shared Public Entry

## Purpose

The first complete quantized-KV inquiry directly compares two internal online
schedules. It does not include the work needed to admit an actual GGML call.
This successor prepares that missing measurement without changing the running
inquiry or enabling a new production path.

The successor keeps the same real KV-head-0 group: six Query heads, D128, 128
visible tokens in capacity 256, separately for Q8_0 K/Q8_0 V and Q4_0 K/Q8_0 V.
It keeps the original four-trial ABBA order, all 768 output words per trial,
original golden data and tolerances, scalar guards, same-mode bit/FCSR/VCSR
checks, and original production quantization, V decoding and PV primitives.
It is not a whole-model run or an untouched whole-GGML operator baseline.

## What The Timer Includes

Baseline: original Query quantization, head-major QK, online Softmax, scalar
Q8_0 V decoding, production RVV PV and drain.

Candidate:

1. Read current vstart/FRM.
2. Map actual `ggml_tensor` metadata through `akv_quant_ggml_map`.
3. Enter `akv_quant_native_execute`, including workspace, capability, shape,
   stride, alias, mask, Query-range and finite-KV-scale admission.
4. Quantize the original Query and execute shared-head QBS QK, online Softmax,
   unchanged scalar V decode and production RVV PV.
5. Drain completion before reading the end counter.

GGML tensor construction and once-per-program capability discovery are outside
the interval, as they are not repeated per operator in a normal backend. The
mapping and all per-call admission scans are inside. `rdcycle` boundaries have
compiler memory clobbers so metadata loads/checks cannot be hoisted across the
timer. Hardware drain/fence instructions remain in place. No speedup is inferred
from the source alone; admission may offset the internal schedule's benefit.

The public runtime uses the existing C implementation, compiled with explicit
contraction-fast and no fast-math, matching the original inquiry's schedules and
production primitives. Existing F16 AKV source flags are not changed. Original
golden checks and actual output-difference reporting remain mandatory.

## Workspace And Fallback

The public ABI reports 4,352 required workspace bytes in this pinned build. The
bare-metal test reserves an aligned 8 KiB bounded software array, passes only
the reported required bytes, and refuses a size/alignment contract it cannot
satisfy. This is ordinary test RAM, not a new SRAM or hardware resource. The
benchmark includes native workspace validation but does not time heap allocation.

The test never silently retries an ordinary implementation after native work
has begun. Admission or execution failure is an explicit failed trial. Native
reports must show selection success, one completed KV group, eight command
attempts, 128 V decodes and successful execution. QBS hardware records must also
prove those commands; software counters alone do not establish execution.

The candidate deliberately retains the original scalar V decoder. The separate
RVV V-decode experiment must pass and show useful benefit before replacing that
callback, otherwise two changes would be conflated.

## Acceptance And Current State

`check_common_attention.py` requires the additional public-entry records and
then calls the unchanged `check_attention.py` full numerical/work checker. It
rejects missing, duplicate or failed admission records; wrong workspace/timed
scope declarations; native work attributed to a baseline; corrupted original
golden comparisons; malformed QBS records and failed UVM summaries. Synthetic
checker tests are not DUT acceptance evidence.

`build_common_attention.py` compiles the shared C runtime afresh, includes the
real GGML headers and unchanged captured mask, pins all dependencies and checks
ELF bounds and required symbols. It emits a distinct
`COMMON_ENTRY_BUILT_NOT_EXECUTED` state: the old internal-schedule worker must
not accidentally admit it without the new checker and prerequisite gate.

Current prepared builds:

- `verification/out/akv-quantkv-common-attention-q8-build-20261024-03`
- `verification/out/akv-quantkv-common-attention-q4-build-20261024-02`

Earlier preparation builds are not execution evidence. No successor VCS task
is launched by this preparation. First accept the original complete Attention
results and assess the measured benefit, then run this public-entry paired
comparison with independent protocol checks before live GGML integration.
Existing full-Attention and V-decode tasks retain their sealed source inputs.
