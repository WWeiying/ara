# AKV REFILL overlap: implementation contract

Status: implementation design, not an enabled RTL feature. Baseline: signoff
commit `514b798a`. Do not change the sealed RTL/runtime while the production
packing projection twins are consuming their source manifests.

## Evidence and the actual software boundary

The completed probe is archived in
`verification/akv/results/refill-overlap-baseline-20261023.json`.
Its immediate REFILL is presented 78 cycles before the last older FMA completes,
but allocates only after that completion. Both controls take 756 joint cycles.
This establishes an admission opportunity, not a real Attention speedup.

Production Decode currently follows this sequence in
`software/akv/src/akv_v2_native_riscv.c`:

1. FULL or REFILL the current tile.
2. Compute QK and store scores in the workspace.
3. Apply mask, scale and online softmax.
4. Execute PV, store accumulators, and return from the assembly function.
5. Advance the C loop and issue the next REFILL.

The D128/GQA6 F16 PV function ends with six vector stores. The F32 Prefill
function similarly stores six output vectors. Therefore the real loop does
not have the probe's FMA-to-REFILL adjacency. A hardware-only change can have
little or no useful overlap: normal VLSU drain remains mandatory and the stores
depend on those final FMAs. Do not claim the 78-cycle window transfers to this
loop without tracing its actual request sequence.

## Hardware ownership and admission

The first implementation is blocking REFILL with earlier memory execution,
not asynchronous software-visible completion and not concurrent context replay.
FULL, RELEASE, QBS, ordinary memory operations and unsupported arithmetic retain
their existing rules. No new SRAM or command ISA is required for this step.

| Location | Existing mechanism | Required change or invariant |
| --- | --- | --- |
| Dispatcher backend register | A request can remain valid before sequencer allocation | Include this older pending request in admission; allocated VIDs alone are insufficient |
| Sequencer allocation | Running membership is tracked per PE and VID | Record whether each allocated instruction is safe independent arithmetic |
| Dispatcher REFILL decode | `!ara_idle_i` sends the request to WAIT_IDLE | Permit only v2 REFILL when all older allocated and pending work is eligible |
| VLSU command handoff | `normal_vlsu_idle`, exclusive QBS/AKV owner, consumed-request guard | Preserve every condition; early presentation does not authorize a memory transfer |
| AKV context | REFILL overwrites the current tile | All old context replay must have completed, including request/return staging |
| Sequencer WAIT | Latches address acknowledgement and exception | Retain terminal status until all older arithmetic completes |
| Dispatcher FP response | Lane flags and `fp_csr_busy` remain active | Preserve late lane flags, including while REFILL status is held |

Use an explicit initial whitelist of unmasked, ordinary elementwise FP FMA
operations. Do not use `VFU_MFpu` alone: that class also contains operations with
different routing, completion, or scalar-response requirements. Keep reductions,
masked operations, slide/mask consumers, CSR/configuration, memory operations,
and maintenance/reshuffle micro-ops outside the initial whitelist. The existing
sequencer continues enforcing all register dependencies among the older FMAs.

Eligibility needs one bit per live VID, cleared on reset/retirement and written
on allocation. Evaluate all PE memberships, not only lane 0 or an aggregate
MFPU done pulse. The dispatcher-to-sequencer valid register is a separate older
instruction until allocation; classify its actual micro-op, not the current
architectural REFILL. Invalid entries must not retain authority from VID reuse.

## Deferred terminal response

The existing VLSU reports a fill terminal through address acknowledgement and
load completion. The sequencer must allow the fill VID to retire normally while
holding its response. Waiting for global idle while artificially retaining that
VID creates a self-deadlock.

Prefer extending the sequencer's existing WAIT/latched-ack path rather than
introducing a second response buffer in the dispatcher. The present WAIT
branch holds `ara_req_ready_o=0`, retains `pe_req_o`, and does not allocate a
younger VID. Under those invariants a separate older-VID snapshot is unnecessary:
all live VIDs other than the stable current REFILL ID are older instructions.
Use the registered all-PE running vector, excluding ONLY that ID, to delay the
terminal response. This is conservative by one completion-observation cycle
and avoids a new completion-to-response combinational path. The REFILL's own
completion must still satisfy its existing VLSU conditions.

Assert no younger allocation throughout WAIT, stable current ID/op, and no
response while another VID remains live. If later work permits younger
allocation, this simplification becomes invalid and must be replaced by an
explicit age/snapshot contract. A terminal arriving first remains in the
existing acknowledgement/exception registers; older arithmetic finishing first
is represented by the cleared all-PE running bits. Do not use lane 0 completion
or the numerical ordering of VIDs as a substitute.

This extension is pending implementation and tests. Admission must separately
check the dispatcher register's pending older instruction: its contents may
not yet have a running VID. Allocation is ordered, so after REFILL has entered
WAIT, that older request must already have been allocated or completed. Test
same-cycle completion/allocation and VID reuse rather than assuming this from
the high-level software sequence.

After a fault, report the original cause/tval once, with no younger execution
and no outstanding AXI response left behind. Preserve the existing AKV context
invalidation/recovery contract; do not replay arithmetic or add an already
processed tile twice during retry.

## Production scheduling, not only a synthetic probe

After the hardware gate passes, expose the real window through a shared
assembly/runtime entry, not a benchmark-only replacement:

- Prepare the next tile index before the final PV arithmetic.
- Once the final V replay has completed, present REFILL after the final FMA
  group but before dependent accumulator stores.
- Wait for the blocking REFILL response, then perform the original stores.
- Let the C loop skip exactly the already completed next-tile fill.
- The last tile performs no speculative REFILL; RELEASE remains unchanged.

This scheduling changes instruction order and must not be described as identical
instruction execution. It is valid only for private, non-aliasing workspace and
immutable Q/K/V inputs during the call. Establish these requirements at the
runtime boundary. Preserve all per-output FMA/rounding orders and flags. On a
REFILL page fault, older FMA results/flags must be complete before the exception;
following stores have not executed. Resume must retry the faulting REFILL, not
repeat the PV loop. If these memory/ownership requirements cannot be established,
retain the original schedule instead of weakening the hardware barrier.

Start with the shared D128/GQA6 Decode/PV path, then cover the equivalent F32
Prefill path. Generic head groups and D256 have different loop/rounding details;
they retain the old schedule until a separately checked transformation exists.
This initial admission step does not replace the larger objective of overlapping
next-tile fill with current-tile computation or reducing intermediate traffic.

## Acceptance matrix

| Gate | Required evidence |
| --- | --- |
| Admission | Safe allocated and pending FMA cases enter early; memory, masked, reduction, slide and maintenance cases stay serialized |
| Completion | Older work finishes before, after and in the same cycle as success/fault terminal; exactly one response, no deadlock |
| Lane lifetime | Delayed nonzero lane completion cannot release the response early |
| Ownership | No context overwrite while replay is live; no ordinary VLSU/QBS overlap; request accepted only once under backpressure |
| FP/CSR | Exact results and sticky flags; CSR access remains busy until older FP effects are visible |
| Fault/retry | MMU/PMA/AXI error and reset during fill; drain, cause/tval, invalidation and retry checked |
| Real workload | Same captured Q/K/V, outputs, tolerances and tile counts; accepted payload reads precede final old arithmetic completion |
| Performance | Lower complete Attention interval, including software scheduling; not merely lower fill issue delay |
| Regression | Ordinary RVV, QBS handoff, legacy AKV, D64/D96/D128, tail tiles and fallback retain correctness |

Collect a bounded cycle trace of presentation, pending/allocated eligibility,
all-PE completion, command fire, first payload AR, terminal and scalar response.
Join by architectural order plus allocation lifetime; reused VID alone is not
an instruction identity. Reuse the completed baseline rather than rerunning it
without a source/configuration reason. Do not proceed to a broad simulation
matrix until the first experiment distinguishes admission, memory service and
response ordering.
