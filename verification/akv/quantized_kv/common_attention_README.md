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

## Event-Gated Execution

`queue_common_attention.py` pins the prepared build, new worker/checker/tests,
and the predecessor's sealed input inventory. It verifies the actual predecessor
PID and owner script, waits on its Linux pidfd rather than repeatedly reading
simulation logs, and refuses dispatch unless the owner ends with checked PASS.
After the wait, identities are checked again and `exec` transfers the same
systemd-owned process to `run_common_attention.py`. A short-lived launcher never
owns orphan simulator children.

The public-entry worker performs an independent raw replay via
`audit_attention.checked_attention`: original numerical output and flags, QBS
work and timings, independent protocol inputs, image/ELF/source receipts, and
the already accepted multi-head QK prerequisite. It must match the prepared
build's exact original inquiry and profile. A green summary alone is insufficient.

If that checked internal inquiry is not faster than its paired ordinary path,
the successor records `NO_BENEFIT_NOT_RUN`, preserving the predecessor's
functional success and measured cycles without spending another long simulation
on an unpromising promotion. This is not a numerical failure or a filtered-out
measurement. Any failed prerequisite or identity check prevents downstream VCS.

When launched, the public-entry inquiry retains the three-hour VCS bound and
requires actual zero simulator exit, complete numerical/native-entry/QBS work
records, independent CVXIF/backend/AXI read/write checks, and matching source and
image identities after execution. A public-entry functional PASS can still show
a slowdown; the worker records it and does not enable GGML dispatch automatically.

`test_common_attention_run.py` tests typed-build rejection, unchecked-predecessor
rejection and the no-benefit/no-simulator path. `test_queue_common_attention.py`
tests failed-owner blocking and direct exec ownership. Together with the four
numerical/work checker tests, nine host tests pass. These tests exercise worker
control logic with mocks/synthetic transcripts, not additional RTL workloads.
