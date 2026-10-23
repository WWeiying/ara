# AKV REFILL overlap: implementation contract

Status: restricted candidate wired in the verification worktree; real sequencer
unit checks pass, full-SoC probe and production scheduling remain pending.
Baseline: signoff commit `514b798a`; the pre-integration state is retained at
`5ed0f7e6`. Do not modify helpers, ELFs, images or software sources pinned by
active consumers. Existing Q8_K runs use the previously compiled image and
do not consume the modified dispatcher/sequencer source at runtime.

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

The candidate connection is implemented but not yet accepted end to end. Admission must separately
check the dispatcher register's pending older instruction: its contents may
not yet have a running VID. Allocation is ordered, so after REFILL has entered
WAIT, that older request must already have been allocated or completed. Test
same-cycle completion/allocation and VID reuse rather than assuming this from
the high-level software sequence.

### Audited connection points

`akv_refill_order_guard.sv` is now in the Bender source list and connected to
the real sequencer and dispatcher through `ara.sv`. Its isolated VCS gate passes 4104
checks (4096 classification/live/pending/current-ID combinations plus eight
temporal boundary checks). Reproduce with:

```sh
python3 verification/akv/run_refill_order_guard.py --output /absolute/new/output
```

The retained receipt is
`verification/akv/results/refill-order-guard-20261023.json`. It proves the guard
equations, reset and tested VID reuse behavior, not the all-PE aggregation,
actual FMA classifier, precise fault retirement or a speedup in the processor.

| Actual RTL point | Integration obligation |
| --- | --- |
| `ara_sequencer.p_vinsn_running` | It already ORs every lane, load, store, slide and mask PE into the registered `vinsn_running_q`; use that full vector, not `pe_resp_i[0]` or lane 0 membership. |
| `ara_sequencer.p_sequencer`, successful allocation | Record eligibility where the VID is allocated and its PE memberships are set. The verification-only `verify_vinsn_alloc` is not an architectural control signal. |
| `ara_dispatcher` registered `ara_req_o/ara_req_valid_o` | This is the older pending request. Include it even when no VID has been allocated. Keep request/token behavior unchanged. |
| `ara_dispatcher` `decode_blocked` cleanup | A stalled backend suppresses speculative decoder results and restores normal state. Do not derive new admission state from speculative requests that this cleanup discards. |
| `ara_sequencer` memory WAIT response condition | Add the older-drained condition to response release, not to retirement of the REFILL's own load VID. Preserve latched ack/exception and one-response behavior. |
| `vlsu.normal_vlsu_idle` and command handoff | Preserve all address generator, VLDU/VSTU, prepare-inflight, AXI-cut and response checks, plus QBS/AKV exclusive ownership and request-consumed tracking. |
| `vlsu.akv_command_early_ack` | Existing early acknowledgment applies only to local LOAD/COLUMN_LOAD. It is not authorization to acknowledge REFILL before faults and older arithmetic are resolved. |

The proposed initial classifier accepts only unmasked ordinary
`VFMACC/VFNMACC/VFMSAC/VFNMSAC/VFMADD/VFNMADD/VFMSUB/VFNMSUB`, with no
conversion, overlap-capture or source-snapshot repair metadata. Selecting
`VFU_MFpu` alone would incorrectly include other instruction families. Existing
hazards remain authoritative for these older operations; eligibility is not
permission to ignore their register dependencies. Actual late-lane fflags
timing must still be joined with retirement before closing the precise-response
gate.

### Candidate integration evidence

`refill_sequencer_tb.sv` instantiates the actual sequencer with independent
PE/AddrGen fixtures, not a copy of the control algorithm. The focused VCS run
`verification/out/akv-refill-sequencer-20261023-02/` passes 38 checks and six
terminal-order scenarios: older arithmetic first, same-cycle completion, or
REFILL first, each with success and a latched load-page-fault outcome. It
checks pending-request classification, current-VID retirement, delayed nonzero
lane completion and exactly one scalar response. The first attempt lacked
common-cell counter dependencies and did not run; it is retained as a build
failure, not counted as an RTL test.

The Dispatcher exception to global idle is confined to v2 REFILL and requires
an explicitly true safety input. Unconnected legacy unit fixtures default to
serialized behavior. FULL, legacy REFILL, RELEASE, QBS, masked/unsupported
arithmetic and ordinary memory admission are unchanged. The sequencer records
classification on actual allocation, uses registered all-PE membership and
holds the existing memory response until older work drains. The original VLSU
ownership checks are not relaxed.

`run_refill_integration.py` owns a separate SoC build and then runs the existing
sealed 54-command FMA/REFILL probe. Its service is
`akv-refill-integration-20261023-01.service`; outputs are under
`verification/out/akv-refill-integration-run-20261023-01/`. The old Q8_K image
and outputs are not overwritten. The new image includes verification-only
`AKV_REFILL_ORDER` start/first-payload-AR/terminal records, using the same
cycle counter and architectural-order metadata as the commit monitor. These
records allow actual memory progress to be compared with old FMA completion,
rather than inferring overlap from first presentation or VID allocation.

The short control test is not numerical FMA execution, real Attention latency
or precise fflags validation. The full probe, subsequent representative
regression and shared production PV scheduling are still required. No new
performance benefit is claimed from the candidate connection alone.

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
following stores have not executed. Precise exception order alone does not
prove transparent instruction retry: the current engine clears
`context_ready_q` after a read fault, and another REFILL requires a ready
context. Recovery must therefore re-establish FULL state and restart Attention
with initialized workspace, or a separately specified engine retry mechanism
must be implemented and tested. Simply resuming the faulting REFILL is not an
accepted recovery path. Do not repeat PV on an already accumulated workspace.
If these memory/ownership requirements cannot be established,
retain the original schedule instead of weakening the hardware barrier.

Start with the shared D128/GQA6 Decode/PV path, then cover the equivalent F32
Prefill path. Generic head groups and D256 have different loop/rounding details;
they retain the old schedule until a separately checked transformation exists.
This initial admission step does not replace the larger objective of overlapping
next-tile fill with current-tile computation or reducing intermediate traffic.

### Shared PV scheduling candidate

The shared assembly now emits both the original
`akv_v2_update_outputs_f16_d128_gqa6` entry and a
`akv_v2_update_outputs_f16_d128_gqa6_refill` entry from one macro body. The new
entry takes the next tile start in its fifth argument, issues the existing
blocking REFILL after the final PV FMA group and before accumulator stores,
then performs the original stores. The original entry's 74 instruction
encodings are identical before and after this source refactoring. No extra
branch or REFILL is added to that original entry.

`akv_v2_native_riscv.c` selects this schedule only with the evaluation define
`AKV_REFILL_OVERLAP=1`, D128/GQA6, more than one KV tile and a successful
workspace/KV-disjointness check. It skips exactly the next loop-head fill that
the preceding PV entry completed; the final tile uses the original entry.
Unsupported shapes, aliases and the default define value 0 retain the old
schedule. Inputs must not be concurrently modified during the call.

`akv_refill_schedule.h` checks both K and V address hulls, including row stride,
count, end boundaries and integer overflow. Its twelve host checks are included
in `make -C software/akv check`. The normal runtime, portable Decode suite (192
cases) and online schedule suite (108 cases) also pass; these are host tests,
not hardware numerical execution of the new schedule. Both define values and
the shared assembly compile with GNU RV64GCV/Zfh/Zvfh. Disassembly confirms one
REFILL after the final FMA and before all stores in the new entry. This gate is
recorded in `verification/akv/results/refill-software-gate-20261023.json`.

The new schedule remains disabled by default until real Attention output/flags,
tile counts, numerical fallback, whole-interval latency and recovery are checked.
It is not yet enabled in the production GGML backend or in Linux workloads.

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
