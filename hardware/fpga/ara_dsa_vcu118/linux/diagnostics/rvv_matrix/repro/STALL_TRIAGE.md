# Historical stall triage

For numerical failures, exceptions, mixed observations and earlier failures
outside this ledger, see [ALL_FAILURE_REVIEW.md](ALL_FAILURE_REVIEW.md).
This document alone is not an all-failures review.

## Scope and result

This completes approximate attribution of all **198 historical stalled ELF
identities** in the failure ledger, including originals and operation
partitions. It does not claim 198 independent bugs, complete cycle-level
root-cause proof, successful repair, or completion of the interrupted retest.
The 139 originals not rerun in the latest campaign are classified from their
older recorded stalls; they were not silently marked tested again.

Evidence base: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
`stall_family_triage02/triage.json` contains every name, ELF/report SHA256,
PC/opcode, last printed trial when present, snapshot checks, classification
and confidence. `ledger.json` freezes the input. All 198 ELF identities and
198 no-retirement snapshot pairs verified. No record is left unclassified.

The collector uses the latest matching stalled report, falling back to a
historical report. Early reports without diagnosis.name are accepted only
when their final result names the stalled case. A printed trial can precede
several operation calls: it is not automatically the exact unreturned call.

| Group | ELF records | Approximate attribution | Confidence |
|---|---:|---|---|
| Masked slides | 85 | MASKU/SLDU disagree on stream origin/count for restart; stride trimming can compound it | RTL mechanism confirmed; individual records linked by opcode family |
| Large-group arithmetic/merge/compare restart | 45 | Archived lane sequencer trims the packed mask stream, but consumers retain a zero-based stream | Strong static candidate; 33 have VL512/vstart256 print, 12 only opcode/family evidence |
| Mask logic source alias | 3 | Global MaskM override also truncates an actual mask-logic source, not just a predicate | Static candidate |
| Gather variants | 11 | Packed-mask supply and gather index/request/data token accounting | Candidate; no exact trial printed, keep alternatives open |
| High-end widening extension overlap | 42 | Overlap maintenance/source-lifetime dependencies fail to drain or issue/complete the original | Candidate; exact blocked state not captured |
| Kernel vector-state wait | 3 | Kernel CSR waits for vector idle after a fault/replay path leaves outstanding vector state | Boundary established; underlying unit unproven |
| Segment alignment request | 9 | Segment request acceptance/completion, mask/address or trap cleanup boundary | Boundary established; exact internal cause unproven |

## A. Masked slides: confirmed RTL mechanism

See `../../README_mask_slide_restart.md` and `mask_slide_archived_cause01`.
Joint MASKU/SLDU simulation, including archived module versions, confirms
three restarted cases stall while their three vstart=0 controls complete.
For e32/VL16/vstart8, MASKU supplies one aggregate mask beat, SLDU requires
two; it stalls with 32 issue bytes and 32 commit bytes remaining, no mask,
valid source operands and an available result queue.

Relevant FPGA source: `src/masku/masku.sv` request count initialization,
and `src/sldu/sldu.sv` SLIDE_IDLE, SLIDE_RUN and mask-ready generation.
VSLIDEUP independently subtracts aligned stride after aligned vstart and
overwrites the mask pointer, so do not assume every slide record has exactly
the same missing-beat arithmetic. Scalar and ordinary slides need separate
repair regression. The 85 records are not 85 individually simulated proofs.

## B. Packed-mask restart: shared archived defect candidate

Use `rvv_stall_archived_rtl/lane_sequencer.sv:1212`, not just the current
working tree, which already contains changes. The archived global override:

```systemverilog
if (operand_request_push[MaskM] && pe_req.vfu != VFU_SlideUnit) begin
  operand_request[MaskM].vstart = pe_req.vstart / (NrLanes * ELEN);
  // vl = ceil((vl - floor(vstart / 256) * 256) / 256), for four lanes
end
```

At VL512/vstart256 it requests one raw mask aggregate at word 1. Archived
MASKU excludes VFU_Alu/VFU_MFpu/VFU_MaskUnit from the vstart count trimming
used for memory/slide consumers. Their mask/data processing still covers
the zero-based VL range. The producer supplies 256 bits while the consuming
path expects 512. This explains the cross-opcode boundary much better than
independent multiplier, merge and comparator failures.

The observed opcodes include vsmul.vv/vx, vmacc with no/first/second/both
source aliases, vfmerge, vmfeq, vmseq and a gather parent. Alias-free vmacc
also stalls, so aliasing alone cannot explain this group. The 12 merge
partitions without a last-trial print remain lower-confidence associations.

Discriminating signals: lane `operand_request[MaskM].vl/vstart`, accepted
raw mask words, MASKU read/commit count and mask pointer, per-lane mask valid
and ready, VFU issue counters, vinsn_done. Expect the last raw word consumed
while MASKU/VFU still need another word. This joint path is not yet simulated
here; do not label it a captured board internal queue state.

## C. Mask logic: source truncation, not ordinary predication

The three vmand.mm alias cases are unmasked mask operations. Lane sequencer
initially requests vs1 on MaskM from zero for mask logic; the archived global
override then replaces that request with vstart-based trimming anyway.
AluB and old destination streams keep their own zero-based word counts.
At the same 256-bit boundary, the mask logic source can end early. Thus
the broad override is suspect even though vm=1: MaskM is carrying source
data here, not v0 predication. Verify source roles before repairing it.

## D. Gather: two contracts to inspect

Eleven vrgather.vx/vi and vrgatherei16 partitions have verified opcode stalls
but no exact final trial. Prioritize the same packed-mask contract for their
large e8/e16 groups. Keep a separate alternative: MASKU issues ad-hoc gather
requests and consumes returned data through MaskB; out-of-range indices must
not consume a response that was never requested. Current masku.sv already has
changes to gate MaskB consumption on `!vrgat_idx_oor_q`; that is not proof
of what the old board did at these exact PCs.

Discriminate with mask supply counters plus vrgat index/request FIFO
push/pop, idx_oor, MaskB valid/ready and instruction completion. Do not turn
the known gather prestart data corruption into a proof of gather deadlock.

## E. Extension overlap: maintenance/dependency chain

42 original/partition stalls involve legal high-end source overlap, e.g.
`vzext.vf2 v24,v25,v0.t` and signed equivalents. Ordinary non-overlap
partitions passed; a VL2 generic overlap case also passed. The measured
VL127 e16/m2 case must not be replaced by the easier VL2 case.

Inspect dispatcher overlap capture/original/fixup states, ara_idle and
request acceptance; sequencer group hazards; operand-requester
hazard_source_lifetime/hazard_wait_complete and result-paced readiness.
`OVERLAP_WAIT_ORIGINAL` waits for both original acceptance and backend idle;
an uncompleted maintenance operation or an incorrect source-lifetime wait
can prevent this transition. Snapshots stop around vsetvli/extension and do
not distinguish pre-issue maintenance from an executing extension. This is
therefore a dependency/completion candidate, not proof of a particular
self-dependency edge. Capture those signals once for a representative case.

## F. Kernel CSR wait after zero-stride replay

Three records stop in kernel vector-state handling rather than at a user
slide or multiply. The accepted Image annotation in ISSUES.md RVV-16 maps
the boundary to `csrr a0,vstart`. Do not disassemble these addresses using
the userspace ELF or a different vmlinux.

Dispatcher OpcodeSystem waits for ara_idle before vector CSR access.
After a memory exception, WAIT_IDLE_FLUSH also waits for idle before flush.
Possible cycle: a faulted VLSU/mask/segment token cannot complete until
cleanup, while cleanup/CSR service waits for completion. Need addrgen
exception/ack, VLSU queue state, store response state, segment field state,
flush FSM and ara_idle to prove this. Historical trap metadata does not
identify the currently blocked transaction. The test's fault handler is
another alternative, especially given previously corrected handler bugs.

## G. Segment alignment acceptance/completion

Nine records stop between a scalar phase marker and a masked vlseg3e*.v.
The phase-marker store can itself fault; head PC has no valid bit. Thus the
load might not have been accepted. Inspect dispatcher acceptance, translation
response, segment field progress, mask consumption, trap recovery and done.
The unrelated nine preparation-load SIGBUS cases are capability/setup
exceptions, not these nine retirement stalls. Do not merge them by width.

## Negative evidence and prioritization

Every selected final snapshot has zero DDR outstanding counts and zero DDR
response error counts. Together with frozen retirement and advancing cycles,
this favors vector-internal completion/dependency waits over a currently
outstanding DDR transaction. It does not prove DDR has no defect or identify
a VFU from the unqualified head PC alone.

Repair order: (1) unify mask-stream origin/count by consumer and source role,
(2) resolve extension overlap completion/dependencies, (3) discriminate gather
request tokens from mask starvation, (4) investigate fault/segment cleanup.
Keep numerical FP flag/prestart failures as separate findings: excess NV in
masked comparisons, missing NV in reductions, masked memory excess faults,
decode rejection and whole-register width issues are not explained merely
by a liveness repair. Existing ISSUES.md retains those findings and software
oracle/capability exclusions. No new RTL change or synthesis was launched.

## Reproduce the inventory audit

```sh
python3 triage_stalls.py --ledger /path/to/results.json \
  --objdump /path/to/riscv64-buildroot-linux-gnu-objdump --out /new/output
python3 -m unittest test_triage_stalls
```

The classification script is an audit aid, not an automatic root-cause
prover. Its confidence field is part of the result and must not be dropped
when passing the table to the verification branch.
