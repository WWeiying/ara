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

## Natural long-K graph acceptance

The focused `--suite natural` mode of `verification/qbs/run_ggml_segmented.py`
adds real GGML graphs with 280 native blocks, rather than only forcing the
device limit below a short tensor. It checks Q4_K K71680 and Q8_0 K8960,
N37, M1/M3/M4, and one/three workers. Each of the 12 graphs runs with global
R4, segment-major R4 at 256 blocks, and the same segmented layout with the
wide-M request enabled. The last configuration must still reject wide-M for
split-K. These are generated functional inputs, not captured-model timing.

Acceptance requires the independent dequantized FP64 scalar arithmetic check,
the original `2e-4 + 2e-5 * abs(expected)` error limit, matching output digests
between all three layouts, exact requested/effective policy, split dispatch,
and complete command work at both K256 and K24. A single-worker segmented
graph must actually issue N32, rather than quietly retaining the old N4 plan.
The report verifies all 12 distinct shapes, not just a count of PASS lines.

Two rejected runs and a discriminating probe are retained under
`verification/out/qbs-ggml-natural-20261023-01/`, `...-02/`, and
`verification/out/qbs-ggml-natural-probe-20261023-01/`. They exposed a test
input-contract mismatch before the segmented policy was selected:

| First global-R4 Q4_K output | Value |
|---|---:|
| Reference-quantized input, sequential FP32 sum | 0.827204585 |
| Reference-quantized input, FP64 sum | 0.82719127619630939 |
| Reference-quantized input, block/split FP32 sum | 0.827156067 |
| Production-quantized input, block/split FP32 sum | 0.827568054 |
| Actual graph output | 0.827568054 |

The reference and production Q8_K payloads differed in four bytes. Disassembly
of `quantize_row_q8_K_ref` contains `vfmadd.vv` for the scaled input plus
12582912 rounding bias; the explicit RVV quantizer instead rounds its multiply
before RNE integer conversion. Thus a reference quantizer is not necessarily
bit-identical to the selected production quantizer near a rounding boundary.
Merely switching the arithmetic oracle to FP64 did not resolve this mismatch.

The natural-K matrix check now uses the actual GGML tail-row quantizer's
payload, independently dequantizes it, and evaluates the matrix in FP64.
Full four-row groups retain the generic/reference preparation path. The
test reports reference-payload differences separately; it does not certify
reference/production quantization equivalence. Layout equivalence is also
checked through cross-run output digests. No library, RTL, tolerance, or
arithmetic order was changed to accommodate this finding. The existing short
nine-profile graph suite retains its original reference input generation.

Run `qbs-ggml-natural-20261023-03.service` completed with 36/36 graphs PASS
and an unchanged source/tool/ELF manifest. Output digests match the global-R4
baseline in both segmented modes. Across each single-worker Q4_K/Q8_0
M1/M3/M4 N37 graph, command count falls from 20 to 4; K256 and K24 each
cover every output exactly once. Maximum error against the selected-input
FP64 matrix oracle is 8.46385956e-5 for Q4_K and 1.54972076e-5 for Q8_0.
These results establish natural split-K software integration, not native
instruction execution, model-quality equivalence or RTL cycle improvement.
Native cross-operator context admission/rejection is recorded below. The
successor checker tests additionally reject wrong per-depth tiling and invalid
context lifetimes; this does not change the archived natural-K simulation.

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
aggregate `fflags`. Run02 below completed this updated native test; the earlier
SoC result above predates the view API.

The new test is owned by user service
`qbs-segmented-view-soc-20261023-01.service`, with evidence in
`verification/out/qbs-segmented-view-soc-20261023-01/`. It reuses the checked
half-scale SoC image and freezes ELF SHA256
`563bfe60b1f9b619e5acc6918af563bbc0aad013ef4c1678c3861cf25587c024`.
An independent source review found no blocking issue in the view addressing,
range checks or local output coordinates. Run01 stopped at its 1,800-second
host timeout, not a reported result mismatch. Its console contains successful
99-output old/new pairs for segments 16 and 3, and the complete five-view,
114-output/guard/flag check for segment 16. At stop, the commit trace was
advancing through a byte-copy loop near cycle 1,228,438, after further completed
QBS commands. The segment-3 view suite and terminal protocol check are not
accepted from this partial run.

Service `qbs-segmented-view-soc-20261023-02.service` replays the identical frozen
ELF and image in a new evidence directory, with a bounded 5,400-second host
budget. No RTL, binary, expected output, trace or checker condition was changed.
This extension follows observed completed phases and continued instruction
progress; it is not a timeout increase used to hide an unexplained stall.

Run02 completed at 2026-10-23 09:33:09 UTC, after approximately 34 minutes
of simulation. Both segment sizes pass all five views, 114 selected outputs,
outside-view guards and flags. The complete paired tests report:

| Forced segment blocks | Global R4 cycles | Segment-major cycles | Exact outputs |
|---|---:|---:|---:|
| 16 | 50288 | 18264 | 99/99 |
| 3 | 271064 | 76411 | 99/99 |

These pairs use the same accepted half-scale SoC image; do not subtract their
cycles from the older split-issue table. The independent terminal checker
reports 2,101 matching requests/responses, 1,524 backend allocations/completions,
4,667 completed reads and 661 matched writes, with no exception, protocol
error or pending transaction. The final source check confirms 458 files
unchanged. The forced K limits still make this a functional/performance stress
test, not a naturally long-K model speedup claim.

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

Natural K beyond 256 blocks and native row views have now passed their stated
gates. Native context admission/rejection and the new matrix-barrier regression
are recorded below. Real-model performance with preparation and packing costs
separated remains outstanding. The segmented switch stays opt-in.

## Native GGML context and matrix barriers

The `--suite context` gate executes custom QBS instructions in the QEMU model,
not the GGML software-emulation callback. It checks 48 graphs: four policies,
six shapes and two epochs that overwrite the same activation allocation with
new values. Shapes cover K2/K7 blocks, M1/M3/M4, identical versus distinct
tensor identities, and one/three software workers on one emulated hart. It
is not a multihart coherency test or RTL timing measurement.

The independent matrix oracle dequantizes the selected production preparation
payload and evaluates in FP64. All projections and their sum must be finite
and pass the existing tolerance. Command checks require every K partition,
N32/N5 single-worker tiles, actual native execution and exact FILL/REUSE/RELEASE
lifetimes. Split-K, multirow and the tested threaded chunks must use DIRECT.
Distinct identities and disabled cross-op policy retain operation-local
FILL/RELEASE; absence of CROSS_OP logs alone is not accepted as proof.

| Segment / cross-op policy | Graphs | Quantization skips | Native commands |
|---|---:|---:|---:|
| 0 / enabled | 12 | 4 | 80 |
| 3 / enabled | 12 | 2 | 224 |
| 256 / enabled | 12 | 4 | 80 |
| 256 / disabled | 12 | 0 | 80 |

The initial run is `verification/out/qbs-ggml-context-20261023-01/`.
After the matrix-barrier fix, `qbs-ggml-context-fixed-20261023-01/` passes
the same 48 graphs, with the source manifest unchanged. These counts prove
selection and reuse, not model speedup.

### Reproduced graph self-wait and scoped repair

A projection -> MoE -> projection graph exposed a software ownership bug.
Lookahead skipped `MUL_MAT_ID`, retained the first projection's context for
the last projection, and the intervening expert kernel waited for it to be
released. The release could not execute until that expert kernel returned.

The N4 expert control completed because it did not need a resident context.
With N36, `qbs-ggml-barrier-probe-20261023-02/` timed out after the expert CALL.
The discriminating `qbs-ggml-barrier-wait-20261023-01/` adds a wait-entry trace:

```text
GGML_RISCV_QBS_CONTEXT_WAIT graph_epoch=1 owner_epoch=1 generation=0 m=1 n=36 k_blocks=2
```

Lookahead now stops at `MUL_MAT_ID` and at identity-ineligible `MUL_MAT`
nodes, which may acquire an operation-local context for a tail. Adjacent
compatible projections retain reuse. There is no RTL, descriptor, numerical
order or tolerance change. The trace is enabled only with lifetime tracing.

`qbs-ggml-barrier-fixed-20261023-01/` passes all eight native graphs, across
the same four policies and two input epochs. Each checks 111 projection/sum
values plus 36 expert outputs and issues six native commands in exact
projection/expert/projection order. Each operation independently fills and
releases its context. No cross-op reservation or wait occurs across MoE.

This is a scoped deadlock repair. The in-place/alias boundary is addressed
separately below. Batched-plane tails, graph cancellation and multihart
operation are not proven by these graphs.

The native runner requires an incremental QEMU build receipt tying the binary
to audited ABI/reference/model source hashes. It also checks the configured
source root and the actual Ninja compile inputs for `qbs_ref.c` and
`qbs_helper.c`. The original context run preceded receipt enforcement; the
fixed runs include the receipt, and their unchanged build configuration was
subsequently checked with the stronger source-association guard. No archived
run is relabelled as a new simulation. The successor checks have 48 dispatch
unit tests and eight build-receipt rejection tests.

### Activation mutation between consumers

`qbs-ggml-alias-probe-20261023-01/` reproduced a stale-activation bug in an
actual graph: projection -> in-place SCALE(0.5) -> projection. Tensor identity,
data pointer and graph epoch all remain unchanged. The input check proved
that 512 input words changed correctly; the second projection incorrectly
skipped quantization and returned 0.371987492 instead of 0.18599376677132584.
The guest exited 134; a zero QEMU process exit does not make this a pass.

Lookahead now stops when an intervening output storage span intersects the
activation span. Metadata-only views do not write; custom callbacks and
optimizer operations are conservative barriers because writes may extend
beyond their result tensor. Ordinary disjoint writes retain reuse. This is
a software lifetime fix: no RTL, arithmetic, quantizer or tolerance change.

`qbs-ggml-alias-fixed-20261023-01/` passes 32 native graphs: whole-input
in-place writes, offset-view writes, disjoint writes and pure offset views,
four policies and two epochs. Each graph checks actual input changes, all
111 projection/sum outputs against the independent FP64 matrix oracle,
native command work and exact context access/quantization-skip behavior.
The latter two scenarios require reuse where enabled, preventing a blanket
disable from passing as a repair.

`qbs-ggml-context-alias-regress-20261023-01/` passes 48 context graphs and
`qbs-ggml-barrier-alias-regress-20261023-01/` passes eight expert-barrier
graphs. All three source manifests remained unchanged. These are native
QEMU functional results, not RTL cycles or full-model performance claims.
CPY/SET aliases, custom callback side effects and graph cancellation are not
individually exercised by this set. The barrier policy must be reviewed when
adding a GGML operation that writes outside its result storage.
