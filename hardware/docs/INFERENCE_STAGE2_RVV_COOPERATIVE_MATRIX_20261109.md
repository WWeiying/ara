# Stage 2: QBS and RVV Integer Matrix Coexecution

## Status and Baseline

This is an implementation and validation plan, not a measured speedup claim.
The frozen starting commit is `b0156f8ab`. It preserves the accepted QBS,
AKV, ordinary RVV, and runtime fallback paths. The previous fixed-capacity
activation-replay proposal remains an optional supporting optimization; it is
not the main performance mechanism in this stage.

The active goal is to accelerate complete Prefill projection calls by using
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
model projections. Their software-call cycle reductions remain unmeasured;
the engine-level result must not be advertised as a model speedup or as
meeting the complete-call retention target.
