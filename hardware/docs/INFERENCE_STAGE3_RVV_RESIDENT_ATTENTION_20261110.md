# Stage 3: Shared RVV Execution for Resident Attention

Status: implementation in progress; no new performance or hardware acceptance.
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
unchanged. The unfinished PV boundary test is a prerequisite, not a waived case.

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

The proposed QK encoding and detailed geometry are in
`verification/performance/resident_rvv/qk_shared/PLAN.md`. They become an
accepted contract only after decoder, SDK and RTL validation, not merely by
adding constants. PV encoding, architectural VL/VTYPE and ordinary RVV remain
unchanged. Capability/default promotion is gated by composed results.

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

Unresolved points at entry: the original PV boundary firmware has reported
failures; the QK lane file is only an uncompiled draft; the production reader,
central controller, VMFPU format selector and architectural QK path are not yet
implemented. No gate is marked complete until its evidence has been inspected.

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
The independent QK architectural worker is executing on the checked SoC image.
The complete-Attention smoke passes all 256 bitwise output checks, flags,
memory guards and independent protocol checks; its single candidate call is
29,725 cycles. Paired ABBA performance remains unmeasured: preparation stopped
on JSON integer-versus-string lane-key comparison, with all actual evidence
otherwise matching. This is a report-replay issue, not a new arithmetic failure.
Runtime admission and tile mapping have host tests; they are not yet a native
Attention executor or a promoted runtime capability. Capability remains zero.
Detailed receipts and limitations are recorded in
`verification/performance/resident_rvv/qk_shared/RESULTS.md`.
