# Stage 2: QBS and RVV Integer Matrix Coexecution

## Status and Baseline

Status: the scoped implementation and evaluation are complete. The candidate
remains default-disabled: the complete-call performance target was not met.
This is not a new FPGA delivery or whole-design signoff.

This document records the design, validation plan, and scoped measured results.
The frozen starting commit is `b0156f8ab`. It preserves the accepted QBS,
AKV, ordinary RVV, and runtime fallback paths. The previous fixed-capacity
activation-replay proposal remains an optional supporting optimization; it is
not the main performance mechanism in this stage.

The stage evaluates accelerating complete Prefill projection calls by using
the existing lane integer multipliers alongside the QBS dot array. No larger
SRAM, wider external bus, or replicated large multiplier array is authorized.
No synthesis or new board campaign is required for this stage.

## Mechanism and Numerical Contract

The current QBS array produces at most 32 signed INT8 products per cycle.
The lane integer multipliers are separate hardware. The candidate sends one
decoded weight tile to both resources and assigns independent activation
rows to them. A representative M8 tile assigns rows 0 through 3 to QBS and
rows 4 through 7 to the lane multipliers.

The existing M8 implementation already reuses weights, but time-multiplexes
two activation waves through one dot array. The proposed benefit is concurrent
execution of those waves, not a new claim for the existing weight reuse.

The lane interface must export complete 16-bit INT8 products; the truncated
8-bit result of a standard VMUL is insufficient. Signed products use both
operands' signed interpretation. Each output retains the original subgroup
boundaries, integer correction, scale operations, K order, FP32 rounding,
exception flags, and atomic command completion. No floating-point partial
sums from independent K ranges are reassociated.

## Constraints Checked Before Integration

1. Reuse the existing two activation banks for the two input-row groups.
   This does not require the complete K dimension to fit in the activation
   context. DIRECT remains available for larger working sets.
2. Keep the existing 128 result accumulators. M8 therefore uses N at most 16;
   comparisons against M4/N32 must cover the same total output coordinates.
3. The two integer tile contexts currently hold 16 streams each. Assess
   reusing them for the concurrent waves before adding more subtotal state.
   Doing so reduces the context capacity available to overlap later tiles.
4. With M4 per wave, a 32-element subgroup lasts 16 issue cycles. Two waves
   produce 32 correction requests, matching the existing two-per-cycle
   correction capacity. A 16-element subgroup lasts only eight issue cycles
   and would require four corrections per cycle. The first candidate targets
   Q4_K; shorter-subgroup formats keep the original path unless an explicit
   safe throttling policy is validated.
5. The single FP arithmetic issue path and 16-entry request table may become
   limiting even when integer products double. Measure complete calls,
   including integer drain, FP drain, memory service, and commit.
6. Lane borrowing needs explicit ownership, registered transport, response
   accounting, backpressure, reset, and fault drain. A custom command must not
   consume or overwrite ordinary RVV operations or architectural results.
7. Both the conventional and shared lane multiplier configurations must keep
   their normal instruction semantics. New interfaces remain inactive by
   default until the composed integration is validated.

## Implementation Milestones

| Milestone | Deliverable | Acceptance |
|---|---|---|
| A | Full-product interface on existing multipliers | Independent arithmetic checks, all EEWs, signedness, stalls, reset, original result interface |
| B | Exclusive lane multiplier borrowing and registered return | No duplicated multiplier array; ordinary execution and owner transitions correct |
| C | Concurrent Q4_K activation-wave scheduler | Correct subgroup/result tags; no overwrite, loss, duplicate completion, or fault leak |
| D | Composed engine and SoC tests on real model inputs | Same output coordinates, result bits/flags, total work, full K and complete-call accounting |
| E | Runtime selection and delivery | Keep fallback, validate different projections/shapes, pin RTL/SDK/input/image versions |

## Experiments and Stop Conditions

Use VCS on the host. Run the necessary independent component checks in
parallel, then a small composed test before spending time on SoC simulation.
Use real distinct activation rows, not copies of a single token. Include at
least an Attention projection and an FFN projection, with different K/N
shapes. Qwen3 samples are preferred when complete provenance is available;
older Qwen2.5 samples may supplement debugging but must be labeled as such.

Compare both the original M8 schedule and an equal-work pair of original M4
calls. Include all input loads, setup, correction, accumulation, and result
commit in the corresponding measurement scope. Engine-only, SoC, and model
times are different measurements and must not be substituted for one another.

A 20 percent cycle reduction on representative complete projection calls is
the candidate retention target, not an existing result or an unconditional
promise. If shared delivery, correction, or FP accumulation prevents useful
net gains, retain first-failure and performance evidence and revise the
mechanism before expanding hardware. Do not enlarge SRAM or advertise a
model-level speedup to hide a failed hypothesis.

Long runs use independent service-owned output directories. Confirm actual
simulator execution once, then avoid polling simulations expected to take
more than ten minutes. Preserve unrelated working-tree changes and never
alter sealed inputs of an active worker.

## First Measured Engine Gate

The first paired engine check is complete. Its receipt is
`verification/out/stage2_matrix_vcs_20261109_02/report.json` in the signoff
worktree. It reuses the original compiled images after a separately recorded
parser-only audit; the original worker's FAIL report is preserved. Both
configurations pass the unchanged numerical and exception checker, the
synthetic and context suites, and the same-coordinate real-data cases.

For eight distinct Qwen2.5 input rows, K=1536, and N=32, two original M4/N32
commands cost 13,756 engine cycles. Two original M8/N16 commands cost
15,362 cycles; the cooperative M8 pair costs 12,238 cycles. This is a 20.34
percent reduction relative to original M8, but an 11.04 percent reduction
relative to the faster equal-work original M4 schedule. M4 cycles are
unchanged with cooperation enabled. These are engine-command measurements,
not whole software projection calls or end-to-end model acceleration.

The original and cooperative M8 command perform identical memory work and
FP operations. Integer dot issue cycles halve, but integer-result requests
blocked at the FP interface rise from zero to 1,296 cycles per M8 command.
This identifies the next constraint without justifying additional SRAM or a
duplicate FP array. Qwen3 Attention/FFN cases, full-FP coexistence, and
complete SoC/SDK call accounting remain required before acceptance.

## Validated Supporting Decoupling

The follow-up `stage2_matrix_queue_vcs_20261109_01/report.json` passes with
fresh queue-depth-zero and queue-depth-16 images. Zero depth reproduces the
previous cooperative cycles. A 16-entry, 140-bit typed FIFO captures the full
integer result and its destination/scale fields before releasing the integer
context. It uses 280 bytes of raw register data, not additional activation or
weight SRAM, and does not duplicate arithmetic arrays. Completion, fault
drain, seed admission, and reset accounting include queued work.

Both real Qwen3 projection samples retain eight distinct rows, K=2048, N=32,
and exactly the same ordered outputs and flags. Original M4 costs 18,216
engine cycles; cooperative M8 costs 16,194 without the FIFO and 13,604 with
it. The final engine reduction versus the faster original M4 is 25.32
percent. M4 fallback cycles remain unchanged. Per M8 command, next-tile
start blocking falls from 2,112 to 816 cycles; waits with only context1
occupied fall from 1,680 to 384 cycles. All 1,024 queued results drain, with
24 starts overlapping queued prior results. This is measured evidence for
context/result decoupling, not an inference from peak product throughput.

The full-FP lane ownership gate also passes after fixing held-request
arbitration and retaining FP/SLDU/flag drain checks. Ordinary RVV and PV
offers take priority until QBS has acquired ownership; the dispatcher still
requires global Ara idle before submitting a QBS command. No ordinary
instruction or private PV result may overlap a borrowed owner.

The complete-call gate uses separate reset-first M4 and M8 programs with
first/repeat trials, real RVV quantization, packing, SDK planning, native
execution and final fence included. Attention Q uses N64 and FFN gate N128,
both at M8/K2048. These are bounded output-channel slices, not complete
model projections. Their measured software-call results follow below; the
engine-level result must not be advertised as a model speedup.

## Complete-Call Disposition

The paired SoC campaign `stage2_soc_campaign_20261109_01/report.json` is
`PAIRED_CALLS_CHECKED`. Both smoke arms and all eight projection workers pass
their output, exception, protocol, image and input-identity checks. Both SoC
images use the same `bcc2e0082` source archive, differing only in the
cooperation flag. The same-mode ELF is identical between hardware arms.

| Projection slice | Trial | Original M4 | Original M8 | Cooperative M8 | Reduction vs. fastest original |
|---|---|---:|---:|---:|---:|
| Attention Q, N64 | First | 171,793 | 176,124 | 162,520 | 5.40% |
| Attention Q, N64 | Repeat | 170,361 | 174,676 | 161,072 | 5.45% |
| FFN gate, N128 | First | 210,577 | 219,767 | 192,559 | 8.56% |
| FFN gate, N128 | Repeat | 208,733 | 218,445 | 191,237 | 8.38% |

M4 cycles, including every software timing segment, are unchanged with
cooperation enabled. For an identical M8 ELF, Attention saves 13,604 cycles
per invocation and FFN saves 27,208. Each saving is entirely in execution
and equals the reduction in engine busy cycles; quantization, packing,
planning, fencing and software execution remainder are unchanged. The four
actual lane multipliers each accept and return 32,768 beats in the two
Attention trials and 65,536 in the two FFN trials. M4 borrowed work is zero.
Special-scale checks also pass using the original numerical/flag checker
with a separately audited final-output canonical-NaN adapter; details and
the inherited half-sNaN limitation are in `MATRIX_SPECIAL_GATE.md`.

The **20 percent complete-call retention target was not met**. Preparation
occupies 81.24 percent of the cooperative Attention repeat call and 68.98
percent of the FFN repeat call. The mechanism is retained as an explicit,
default-disabled candidate, not promoted to the validated FPGA delivery.
No extra SRAM, external bandwidth or replicated arithmetic array is added
to chase the target.

These are complete SDK microbenchmark calls using genuine model inputs and
the real llama RVV quantizer, not full GGML operators. The firmware performs
row-wise quantization followed by packing; GGML can instead use direct M4
interleaved preparation or prepared reuse. Consequently, the table is not
a measurement of GGML preparation costs, a full-width projection, or model
inference speed. Runtime selection still requires the existing explicit
wide-M option and capability/shape admission; the new RTL does not silently
enable it or alter fallback selection.

## Runtime Functional Closure

`stage2_ggml_functional_20261110_02/report.json` passes a real single-worker
GGML `mul_mat` graph using the captured raw Qwen3 Attention tensors. Frozen
llama `03959acc0` and SDK `c2b7db195` are built privately, without live dirty
sources. The four independent native-QEMU processes exercise wide M8,
default M4, shape fallback to M4 and ordinary RVV. Actual QBS command counts
are respectively 4, 4, 2 and 0. Every prepared activation byte is checked
against the corresponding layout oracle; QBS outputs/flags are exact and
RVV is checked against a predetermined numerical tolerance. The host
arithmetic oracle and QEMU share the pinned QBS reference, so this proves
GGML preparation/selection and native ABI behavior, not independent
arithmetic correctness or new RTL speed.

The original standalone-configure failure is preserved. Its successor uses
a test-side parent CMake project to build the unmodified frozen GGML in
its normal embedded mode, avoiding the absent standalone package template.
No production source or numerical checker is changed. Optional QBACC is
excluded after an exact ABI-extension compatibility audit; ordinary QBEXEC
alone is exercised. The functional gate and the paired VCS measurements
are separate evidence sets and must remain separate in later reporting.

## Configuration and Deployment Contract

The borrower is a fixed-latency transport, not an independently stalled
multiplier queue. A beat admitted by all four lanes returns three cycles
later. The normal EW8 core must therefore have zero internal pipeline stages.
`QbsLaneMulLatencySupported` now gates the top-level selection, the VLSU
cooperative scheduler and the VMFPU borrower together. With a retimed normal
EW8 core, the design selects the original QBS schedule instead of issuing
work into an incompatible borrower. The shared multiplier explicitly pins
`Bypass8=1`, rather than depending on the module's default parameter. Existing
ownership rules still drain its ordinary pipeline before the bypass is used.
This is configuration protection, not support for variable return latency.

| Hardware selection | Software selection | Execution |
|---|---|---|
| Cooperation off or unsupported | Wide-M off | Original M4 or smaller-row schedule |
| Cooperation off or unsupported | Wide-M admitted | Original serial M8 schedule; still a legal command |
| Cooperation supported and on | Wide-M off | Original M4 or smaller-row schedule; no borrowed products |
| Cooperation supported and on | Q4_K/M8 admitted | Concurrent input-row waves and the 16-entry integer-result FIFO |
| Cooperation supported and on | Other profile or M other than 8 | Original schedule |

Wide-M admission requires the existing explicit `GGML_RISCV_QBS_WIDE_M`
option as well as shape, layout and device checks. The SDK's recommendation
estimates input payload reduction; it does not model preparation latency or
prepared-data reuse, and it does not report the new RTL switch. In particular,
M8 capability is not a promise that M8 is faster than an optimized M4 caller.
There is no new ISA field or capability bit in this stage. Both the hardware
cooperation and software wide-M option remain off by default. Shape/type
fallback is selected before execution; a fault after native execution starts
is not automatically retried as ordinary RVV.

The complete-call results above remain tied to source revision `bcc2e0082`.
The later configuration guard does not change the enabled expressions in
those measured standard/shared latency-zero configurations. Its directed
validation is separate from that earlier SoC measurement; it must not be
reported as a new whole-SoC performance run.

`stage2_vmfpu_config_20261110_01/report.json` passes all four fresh VCS
configurations, with source and image hashes checked before and after use.
The unchanged full-FP checker passes for standard/shared latency-zero cores:
each retires five native FP operations, two PV returns and 24 borrowed
results, including held requests, delayed VRF grants, flags and SLDU drain.
With the ordinary EW8 latency changed to one or two in isolated test inputs,
each actual VMFPU retires eight native VMUL/VMULH instructions across all
four EEWs while a persistent lease/borrow offer is ignored. Neither negative
configuration accepts or returns a borrowed beat. Top/VLSU selection is
checked structurally; these tests execute the lane, not a new whole SoC.

The unchanged SDK also passes `make -C software/qbs check`, using a separate
build directory `stage2_sdk_host_closeout_20261110_01`. This includes layout
capability fallback, 56 format-conversion combinations, 1,530 segmented
address/execution shapes, 1,809 storage-view shapes and 7,187,468 context
admission plans. These counts describe host software checks, not RTL tests.

## Seeded Continuation and Final Disposition

`stage2_seeded_coop_vcs_20261110_04/report.json` passes eight directed engine
commands: six successful commands, one read fault and one reset with a nonempty
integer-result FIFO. Four actual lane multipliers provide 6,272 paired lender
issues and returns. The seed source models the lane interface; this is not a
new ISA-level QBACC or whole-SoC test.

The test captures accepted architectural writes and uses those nonzero values
as the next command's seed. Ordered continuations match the unchanged reference
executing monolithic K-block counts of 1, 3, 5 and 7. The N5 tail uses only active
columns; poisoned inactive seed slots cannot introduce flags. Per-command flags
exclude earlier prefix work, and 104 seed-clear checks include 72 following a
previous NX result. A next request remains held for 344 cycles while the old
FIFO contains work; reset cancels one queued entry and recovery passes.

The read fault occurs after the FIFO has drained. It proves atomic fault and
recovery following earlier queued work, not fault drain with a nonempty FIFO.
The latter has separate evidence in the earlier queue gate. The final worker
checks source and image hashes before and after execution, and its 18 host
checks pass. Attempt 01 was prepared but not executed; 02 and 03 failed during
testbench compilation and are retained. The successor fixes only testbench
declaration ordering, reset-owned initializers and a sampling-edge counter race;
it does not relax the numerical or exception checker or modify production RTL.

Milestones A through D now have the scoped component, lane and paired-SoC
evidence described above. Milestone E closes selection and source-version
control for an opt-in candidate, not default deployment. The unchanged default
paths, Q4_K/M8-only acceleration, four-lane/VLEN1024 geometry and fixed-latency
borrowing limits remain explicit. Area, timing, power, new-bitstream acceptance,
other-format acceleration and model-level speedup are not claimed.

The stage numbers remain stable:

| Stage | Remaining work | Exit evidence |
|---|---|---|
| 3 | Complete resident QK/PV using the existing lane FPU and shared private accumulator storage; close the earlier PV boundary failures first | Ordered results/flags, tails and ownership recovery; complete Attention calls versus the optimized RVV path |
| 4 | Select measured supporting improvements: fixed-capacity activation replay, preparation/reuse, N tiling, long K, tails, quantized KV and multi-query shapes | Net complete-call benefit on applicable shapes, correct fallback elsewhere; no automatic SRAM growth |
| 5 | Integrate retained candidates into actual GGML selection and deliver a unified version | Representative model/format/context regressions and pinned RTL, SDK, runtime and build inputs; board acceptance remains separate |

Stages 3 through 5 are not started by closing stage 2. The 20 percent target
failure is a result of this evaluation, not an unfinished measurement to be
hidden or an authorization to expand hardware until it disappears.
