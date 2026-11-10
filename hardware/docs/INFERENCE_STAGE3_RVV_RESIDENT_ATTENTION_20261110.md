# Stage 3: Shared RVV Execution for Resident Attention

Status: gates A through F are complete for the scoped experimental candidate.
Architectural, paired complete-call and actual native SDK checks pass. Default
selection and capability remain unchanged; no FPGA or physical acceptance is
claimed.
Starting commit: `7543bbec0` on `ara_dsa`. Stage 2 remains an opt-in candidate;
this stage does not silently enable its integer multiplier borrowing.

## Objective and Scope

Complete QK and PV execution on the existing lane FPU, using the existing AKV
Q/K/V stores and the same lane-private accumulator array. Compare complete
Attention calls against the optimized rotating-register PV and ordinary RVV
QK path. Keep scale, mask, online softmax, cross-tile rescaling and final
normalization in their existing software positions and numerical order.

No larger SRAM, wider external bus, extra FPU array, synthesis, power analysis
or new FPGA campaign is authorized. Source inputs and results go to independent
directories under the sole signoff worktree. Existing failed results remain
unchanged. The original PV boundary test was a prerequisite, not a waived case;
it is now closed through the separate strict audit described below.

## Shared Resources and Interfaces

| Resource | Implementation rule |
|---|---|
| Arithmetic | Reuse each lane's actual `i_fpnew_bulk`; exclusive ownership drains ordinary RVV and QBS work |
| Partial sums | One 16 x 64-bit array per lane, 512 B total; FP16 PV and FP32 QK select its interpretation |
| Query blocks | Reuse the resident reader's two 256-bit entries for up to two query rows; no extra Q array |
| Keys | Read the existing four-column AKV panel; capture each outgoing packet before reusing the panel |
| Values | Keep the synchronous V-row replay and its existing two-entry credit protocol |
| Transport | Reuse the registered payload fanout and lane queues; tag coefficient versus data explicitly |
| Completion | All active lanes reach the result barrier before architectural writes; drain final VRF grants before releasing ownership |

QK supports D64/D96/D128, one or two query heads and T1..T64 per tile. Query
base is explicit and must fit the resident Q-row count. Contexts longer than
64 use existing software tiling, not a larger hardware capacity. Inactive
lanes do not execute or wait for nonexistent packets. Each output follows
increasing dimension order using FP32 FMA and exact internal F16 re-encoding
that preserves signaling NaNs; inactive elements cannot contribute flags.

The tested experimental QK encoding and detailed geometry are in
`verification/performance/resident_rvv/qk_shared/PLAN.md`, retained as the
original design record rather than a current progress report. Decoder, SDK and
RTL checks now cover that contract. PV encoding, architectural VL/VTYPE and
ordinary RVV remain unchanged. The assembly leaves' normal RVV setup/stores
can change VL/VTYPE; their clobber contract is separate from the custom command.
Capability discovery and default deployment are not promoted by this stage.

## Work and Acceptance Gates

| Gate | Required work and evidence |
|---|---|
| A: existing PV boundary | Diagnose the original failures, correct their proven causes and rerun the original scenarios with an independent numerical and protocol audit |
| B: shared lane | Actual FPU tests against independent Spike SoftFloat: PV/QK, rounding, special values, active masks, tails, held requests, reset/abort and ownership transitions |
| C: resident dataflow | Synchronous Q/K/V reads, two-entry reuse, query-base selection, T1/2/3/9/17/64 packet masks, backpressure, context admission and recovery |
| D: architectural integration | Both decoders, register interpretation, no QK source import, exact-PC rejection, flags, prior RVV/QBS/AKV coexistence and complete write drain |
| E: real Attention calls | Pinned real Qwen3 inputs, full D and multiple context tiles, equal-work paired VCS runs including preparation, QK, softmax, PV and final drain |
| F: runtime and delivery | Applicable runtime selection with the existing fallback, reproducible source/build/input identities, scoped documentation and commits |

Use bounded component gates before a fresh SoC build. Reuse an existing image
only when its exact RTL/configuration matches the claim. QEMU may validate
software behavior or supply inputs; its elapsed time is never RTL performance.
Representative complete-call benefit, not peak FMA rate or one fast tile, drives
retention. Do not change arithmetic order to manufacture a speedup, or replace
an optimized software baseline with a weaker one.

Historical unresolved points at entry: the original PV boundary firmware had
failures; the QK lane file was only an uncompiled draft; the production reader,
central controller, VMFPU format selector and architectural QK path were not yet
implemented. The completed gates and their inspected evidence follow.

## Current Checkpoint

The shared QK/PV RTL and ABI are implemented at `9af19508d`. Actual lane-FPU,
synchronous-reader, central-control and decoder checks have passed within their
documented scopes. A fresh four-lane/VLEN1024 SoC image has built successfully;
the stage-two integer borrower stays disabled in that image.

The original PV boundary replay has completed with zero firmware errors and a
passing independent protocol report. Its original overall FAIL is preserved:
the old work checker incorrectly assumes that all layout-maintenance uops are
globally serial. The actual mixed-layout trace uses distinct live VIDs and
drains maintenance before final PV execution. Gate A is now closed by
`stage3_pv_boundary_audit_20261110_01/report.json`: 19 host mutation tests,
all 706 backend lifetimes, unchanged raw-data/CSR/architectural checks and a
recomputed independent protocol result pass. This separate audit preserves the
original FAIL and all original evidence; firmware output alone is not used as
the acceptance criterion.

QK architectural firmware and complete-Attention smoke/ABBA firmware are built.
The QK architecture worker passes 24 successful QK operations, 12 real trap
groups, two PV operations and QBS/RVV postludes, with raw-data, actual masked
write, CSR, independent protocol and source/image checks.
The complete-Attention smoke passes all 256 bitwise output checks, flags,
memory guards and independent protocol checks; its single candidate call is
29,725 cycles. ABBA preparation initially stopped on JSON integer-versus-string
lane-key comparison, with all actual evidence otherwise matching. A separately
reviewed successor preserves the original evidence and passes 19 host checks.
The paired ABBA result now passes: baseline cycles are 35,049/34,341 and resident
cycles are 28,796/28,626. Mean complete-call cycles fall from 34,695 to 28,711,
a 17.2474 percent reduction and 1.20842x speedup. All 1,024 output values,
flags, guards, protocol and source/image identities pass. This scoped prototype
measurement is not whole-model speedup or acceptance of the new SDK entry.
Runtime admission and tile mapping have host tests. An experimental SDK entry
now shares the existing native v2 execution loop and selects the resident QK/PV
leaves only after admission; default-OFF object equivalence and host helper
checks pass. `stage3_attention_sdk_vcs_20261110_01/result.json` now also passes
actual native SDK execution: three complete calls, 1,088 exact FP32 outputs,
FCSR 3/11/3, six Decode entry retirements, four experimental executor entry
retirements, eleven QK and eleven PV commands. The D96 case covers two distinct
KV groups, odd H3 pairing, local query-base reset and a one-token tail. It is
explicitly derived from real inputs, not a separately captured six-head model
layer. Independent protocol and post-run source/image checks pass; the service
exited successfully. Capability remains zero and existing entry points retain
native selection.

The measured 1.20842x prototype benefit supports retaining the explicit
experimental route. The SDK functional gate is not a new performance baseline
or a model-level speedup. Stage 3 is closed; shape/performance expansion and
formal GGML/default integration remain stages four and five respectively.
Detailed receipts and limitations are recorded in
`verification/performance/resident_rvv/qk_shared/RESULTS.md`.
The version composition and gate ledger are in
`hardware/docs/INFERENCE_STAGE3_DELIVERY_20261110.md`.
