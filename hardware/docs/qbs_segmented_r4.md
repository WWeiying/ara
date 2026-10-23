# Segment-major R4 weights for split-K

## Why the existing planner uses N4

Global R4 stores all K blocks for output rows 0--3, then all K blocks for
rows 4--7, and so on. A descriptor describes only its local K length; hardware
advances to the next group using that local length. After splitting a long K,
the global group stride and descriptor group stride differ. Consequently the
original planner uses one four-row group per command. Increasing command N
without changing the stored layout would read the wrong weights.

## Optional software layout

Store all output groups for the first K segment, then all output groups for
the second segment. Each segment itself uses the unchanged hardware R4 layout.
The last segment contains only its remaining K blocks. Each segment pads only
the final output group to four rows; no extra K padding is introduced.

For padded output count `Np`, segment start `s`, local segment length `L`,
global output row `r`, and local K block `b`, the packed block offset is:

```text
s * Np + ((r / 4) * L + b) * 4 + (r % 4)
```

An N tile starting at output row `r0` starts at `s * Np + r0 * L`.
Within that command, hardware still sees an ordinary contiguous R4 tensor.
The storage byte count is unchanged. Formats, descriptor version, instruction
encoding, arithmetic pipelines and hardware capacity are unchanged.

Explicit APIs opt into this representation:

- `qbs_repack_weight_r4_segmented`: pack row-major weights once.
- `qbs_plan_create_segmented_r4`: plan commands for the same fixed segment size.
- `qbs_plan_create_segmented_r4_view`: execute an R4-aligned output-row view
  while keeping the complete matrix's packed base and segment stride.

The segment size is software storage metadata, not a descriptor field. It must
fit the queried device and cannot be silently reduced without repacking. The
original packing/planning APIs retain global R4 behavior. Callers and the
runtime library must be rebuilt together because `qbs_plan_t` gained a field;
this is not binary compatibility with old precompiled runtime clients.

## Numerical and execution boundaries

Each output receives the same K segments in the same order as an original
split-K execution with that segment size. Within each command, integer-dot,
scaling and accumulation rules do not change. Software combines FP32 partial
results in the original segment order. Outputs processed together change,
but per-output arithmetic does not. A match to unsplit-K bit patterns is not
claimed: split-K already introduces different partial-sum boundaries.

Command fault atomicity remains the hardware's existing command boundary.
An operator containing several commands was not atomic before and is not made
atomic here. A larger N command may change which outputs have completed when
an error occurs; callers must still discard/restart a failed operator.

M8 plus split-K remains explicitly unsupported: this change must not bypass
the existing activation-gather and wide-M restrictions. M1--M4 commands,
including M/N tails and M4-grouped activation storage, are the initial scope.
Activation-context eligibility still rejects split-K. The optional GGML
integration below applies the same segment policy to both packing and graph
lookahead; it is not enabled by default.

## Evidence

`make -C software/qbs check` passes existing tests and 1,530 new shape tests.
The new observer decodes each emitted descriptor, reads packed bytes as the
hardware would, and compares every weight/activation byte to independent
row/block patterns. It checks output padding, K/N tails, odd segment sizes,
multirow gather, software accumulation, device limits and invalid contracts.
These are Host contract tests, not RTL arithmetic proof or real-model timing.

For the Q8_0 M4/N32/K8960 planning example with 256-block segments:

| Organization | Commands | Logical activation bytes |
| --- | ---: | ---: |
| Global R4 | 16 | 304640 |
| Segment-major R4 | 2 | 38080 |

Weight bytes and the mathematical work are unchanged. These byte/request
counts do not imply an eightfold cycle improvement.

A sanitizer build was attempted, but the host compiler's ASan/UBSan libraries
are missing. It did not link and is not counted as a successful check.

The native integration app is `llama_qwen25_q8_0_segmented_qbs`. It keeps full
K=896 from a real Qwen2.5-0.5B Q8_0 Prefill capture, selects three input rows
and 33 output rows, and forces software K limits of 16 and 3 blocks. This
bounded test exercises split-K, odd offsets, K tails and N tails without
inventing model tensors. It compares original/new layouts on the same RTL,
checking all 99 output bit patterns, `fflags`, and the captured GGML golden
under the existing tolerance. Timed regions include runtime command setup,
gather and partial summation, but exclude offline weight packing and activation
quantization. Forced segmentation is a functional stress test, not evidence
of speedup on a naturally long-K production model.

Native VCS results are in
`verification/out/qbs-segmented-soc-20261023-01/`. Both layouts ran in the same
frozen split-issue SoC image, before the later half-scale candidate:

| Forced segment blocks | Global R4 cycles | Segment-major cycles | Exact outputs |
|---|---:|---:|---:|
| 16 | 49499 | 18021 | 99/99 |
| 3 | 246379 | 69996 | 99/99 |

Both pairs report identical flags (`1`) and pass the captured golden check.
The independent protocol/backend checker reports PASS: 1,741 accepted requests
and responses, 1,284 completed backend allocations, 3,104 completed AXI reads,
480 matched writes, no exceptions and no pending transactions at completion.
The log's generic `[hw-cycles]` field is zero because this app uses its own
paired timer; only the labelled `QBS_SEGMENTED` cycle fields above are timing
evidence. These forced-split improvements establish a working implementation,
not a production speedup estimate. Naturally long-K and GGML integration remain
the next acceptance gates.

## Thread/expert row views

Ordinary GGML row slicing advances the weight pointer by `start * row_bytes`.
That does not work for segment-major weights: each K segment contains all
storage rows. The view constructor therefore receives `storage_rows` and an
R4-aligned `row_start`, while `problem.n` describes only the local output count.
The executor receives the complete packed base and capacity. Activation,
output, stride and workspace coordinates remain local to the call.

For padded storage rows `P`, K-block offset `s`, current segment length `L`
and local output offset `r`, the descriptor's weight-block offset is:

```text
s * P + (row_start + r) * L
```

The range check uses subtraction to reject overflowing/end-outside-storage
views. Construction and execution validate the full storage footprint, not
just the local chunk. An interior view's inactive R4 lanes may contain valid
neighboring rows; only the end of the complete storage has zero padding.
Hardware's existing logical N must prevent those lanes from changing outputs.
The whole-matrix constructor delegates to this view with start zero. Ordinary
global-R4 plans retain their previous behavior. Callers must rebuild against
the enlarged software `qbs_plan_t`; hardware descriptor ABI is unchanged.

`make -C software/qbs check` passes the existing 1,530 whole-matrix tests plus
1,809 row-view shapes, covering all nine profiles, nonzero starts, adjacent and
interior views, final padding, multi-N-command views, K tails, row-major/M4
activations and invalid ranges. Every case rejects a full-storage-minus-one-byte
buffer before any executor call or output write. These are host addressing
and execution-contract tests, not RTL arithmetic validation.

The native real-capture application now additionally compares five views for
each of its two segment lengths against the whole-matrix bit patterns. It
checks 114 selected outputs per segment, all outside-view output guards, and
aggregate `fflags`. This updated native test is pending execution; the earlier
SoC result above predates the view API.

The new test is owned by user service
`qbs-segmented-view-soc-20261023-01.service`, with evidence in
`verification/out/qbs-segmented-view-soc-20261023-01/`. It reuses the checked
half-scale SoC image and freezes ELF SHA256
`563bfe60b1f9b619e5acc6918af563bbc0aad013ef4c1678c3861cf25587c024`.
An independent source review found no blocking issue in the view addressing,
range checks or local output coordinates. The native result remains pending.

GGML integration must bind packing and dispatch to the same immutable layout
trait, preserve the complete base for GEMV/GEMM/tail/expert dispatch, and use
global row coordinates when packing experts together. A fallback after packing
must understand this layout; ordinary RVV kernels cannot consume these bytes
as if they were their original packed format.

## GGML integration and graph acceptance

The local llama.cpp integration is preserved in
`software/qbs/integrations/llama-segmented-r4.patch`, relative to llama commit
`8ed9403e37f1ceb43c6279cdefef01354eac6fd3`. It deliberately excludes the
pre-existing, unrelated AKV edits. The llama worktree itself is not committed
or pushed by this step.

`GGML_RISCV_QBS_SEGMENT_K_BLOCKS` selects the weight layout at first QBS trait
initialization. Unset or zero preserves global R4. A nonzero value fixes the
segment length for the process; changing the environment after initialization
does not reinterpret existing tensors. The selected immutable trait handles
packing, ordinary matrix dispatch and expert dispatch together. Each dispatch
passes the complete storage base, flattened row count and R4-aligned global
row start. Unsupported expert shapes retain their original admission fallback.

The same frozen policy is used by cross-operation activation-context lookahead.
If it produces split-K, the operation cannot reserve/reuse a context or skip
quantization. M1 explicitly uses row-major activations. M4 prefixes and smaller
tails retain their existing grouped/row-major representation. Wide-M remains
available only when the chosen segment fits all K blocks; a forced split must
not select wide-M even if its environment option is enabled.

`verification/out/qbs-ggml-segmented-20261023-02/` passed the actual GGML CPU
backend graph suite under RVV1024 Linux/QEMU. QBS commands are software-emulated
in this gate; it verifies integration and addressing, not hardware arithmetic
or hardware timing. All four independent processes use the same ELF:
`c2147e2473fb06615dee34416329817a8d35bc5e8a3b58c195e5dcdb9ffa0dcd`.

| Segment policy | Wide option | Matrix graphs | Expert graphs | Result |
|---|---:|---:|---:|---|
| 0, original R4 | 0 | 126 | 2 | PASS |
| 3, forced split | 0 | 126 | 2 | PASS |
| 256, no split for these shapes | 1 | 126 | 2 | PASS |
| 3, forced split | 1 | 126 | 2 | PASS; no M5--M8 commands |

Matrix graphs cover all nine profiles, M=1/2/3/4/5/7/8, N=37, seven K blocks,
and one/three worker threads. Reference results use original row-major weights,
reference activation quantization and scalar dot products; every output must
be finite and within the existing absolute/relative tolerance. Separately, an
independent block-index check verifies packed storage bytes. Requested and
effective layout policies must match, graph-scoped calls must have the expected
K and split flag, and summed output counts must equal the logical matrix size.
Wide policy 256 must execute M8 commands. Output-count equality alone is not a
proof of nonoverlapping ranges; the complete numerical check supplies that
additional evidence.

Expert graphs use Q2_K, three experts with eight output rows each, two selected
experts per token, three tokens, seven K blocks and one/three workers. A
post-run checker additionally confirms all eight graph traces, 48 output values
per graph, split flags, and the N8 command in the single-thread segmented path.
Its eight fail-closed unit tests reject missing work, wrong layout/depth,
disabled splitting/wide execution and old expert command geometry.

The runner rebuilds the target incrementally, records source/runtime/config
hashes and the ELF hash, and rejects source drift. The run02 cache was checked:
its source is `/home/wangwy/llama/llama.cpp` and its runtime is this verification
worktree's `software/qbs`. The successor runner enforces the source-directory
check automatically. The extra expert checks were run against the preserved
run02 log after its owning service completed, without changing that log or
claiming another simulation pass.

Run01 failed in the newly added test oracle before the matrix graphs because
GGML does not register generic Q8_K conversion callbacks. The guest exception
return address identifies that null callback. The test now calls the explicit
reference Q8_K conversion functions, as the existing tests do. No hardware
change or tolerance relaxation was made to pass this failure.

Remaining acceptance gates are naturally long K beyond 256 blocks through a
real GGML graph, native cross-operator context reuse/rejection, and real-model
performance with preparation and weight packing costs separated. The existing
direct K280 test does not substitute for the first gate. The switch stays
opt-in until these gates and the pending native view test are resolved.
