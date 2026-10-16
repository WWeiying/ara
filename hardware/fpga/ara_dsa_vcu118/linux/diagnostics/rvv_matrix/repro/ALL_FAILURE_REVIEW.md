# All failure and stall review

## Scope correction

The earlier 198-record stall review was NOT a review of all failures.
The three pinned inventories contain 871 failed, 198 stalled, 47 mixed and
124 unexecuted ELF records. Original and partition records are not independent
bugs. The 1116-entry retest ledger matches the first three sets exactly by
scope/name/SHA256; the 124 unexecuted records are retained separately.
471 inventory evidence files were rehashed successfully.

Evidence root: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
`all_failure_scope_audit02/audit.json` is the machine-readable reconciliation.
Run `audit_all_failures.py --campaign ROOT --out NEW_DIRECTORY` to reproduce.
Issue routes are indexes for review, NOT automatic causal attribution.

Earlier indexed-load width/fault tests and the original arithmetic-restart
matrix are outside those three inventories. They are retained as supplemental
records, not silently included in the 198. Original reports sometimes end in
`running`; that alone is not a stall diagnosis. RVV-01/RVV-02 in ISSUES.md
retain subsequent diagnostic evidence. Historical kernel-health rechecks
repeat the indexed-load SIGSEGV; they are failed health checks, not independent
atomic/context/IPC RTL defects. This report does not certify every unrelated
historical campaign or every unexecuted inner trial.

## Failed records, including numerical and exception results

| Records | Family | Rechecked attribution and limits |
|---:|---|---|
| 2 | Whole-register move, RVV-03 | Dispatcher uses stored source EEW for move length/width without rescaling architectural vstart. Byte-level board mismatch agrees. Original/detail are separate ELFs, not two causes. |
| 8 | Protected-page/FOF, RVV-04 | Original/detail ELFs have unexpected protected-page faults. Nonindexed address generation lacks predicate suppression. FOF shortening/completion is a separate path; not all failures are explained by predication. |
| 1 | Widening FP reduction, RVV-05 | m8 maps to reserved widened EMUL and unconditional legality rejection. Same opcode/cause2 reproduced at original VL0. Downstream reduction width also needs review before a fix. |
| 9 | Misaligned segment preparation, CAP-01 | All nine reduced scenes match a nonaligned ordinary preparation load. Target segment instruction was not reached. Do not report nine target-segment RTL defects. |
| 11 | Sparse ordered reduction, RVV-07 | Board/reduced triggers lose NV for opposite infinities under mask0x24. New source-level mask-coordinate candidate below. |
| 3 | Large-offset slideup, RVV-08 | Offset=VLMAX-1; isolated all-on and sequence-dependent sparse/all-off scenes must remain distinct. Queued-mask ownership/position is a candidate, not a proven pointer bug. |
| 208 | Nonrestart FP comparisons, RVV-09 and data errors | Excess NV occurs even with all-off predicate; other data symptoms must not be relabeled as flags. Existing SIMD predicate logic means "no masking implemented" is not established. |
| 29 | FP comparison restart, RVV-09/11 | Separate excess flags, prestart-bit corruption and larger-group completion stalls. A wrong mask-result prefix is not evidence of the same flag-path bug. |
| 49 | FP moves/slides, RVV-10 | Prestart overwrite, scalar insertion and completion are distinct contracts. 47 partition reductions match numerical symptoms; remaining parent/detail records overlap them. |
| 19 | Scalar integer comparison restart, RVV-12 | Prefix/single reductions agree on wrong prestart bits. Old-destination fetch origin is a concrete candidate below; not the large-mask deadlock itself. |
| 19 | Aliased vector comparison restart, RVV-13 | Keep old-destination fetch, layout/alias hazards and packed-result merge separate. Oracle-allowed agnostic bits must not be counted as defects. |
| 83 | Gather restart numerical failures, RVV-19 | Single calls match original wrong element/value. Archived gather BE has vm/predicate but no vstart guard while output starts at zero. This does not prove the separate gather stalls. |
| 429 | Unit/strided/segmented fault replay | Missing inactive-element translation suppression explains a subset. Unit, positive/negative/zero stride, segment splits and FOF/cleanup are not one established cause. Current-oracle single matches do not prove uninstrumented original per-trial equivalence. |
| 1 | Indexed NF7 replay, RVV-15 | One original check mismatch remains separate. No direct internal cause established; do not substitute a unit-stride reproduction. |

The table sums to 871, not 871 independent RTL bugs. Some stalled ELFs emitted
numerical errors before stopping; both symptoms remain in their raw evidence.
An earlier printed error is not necessarily the last unreturned trial.

## Stall records

See STALL_TRIAGE.md for all 198 identities and seven candidate groups:
85 slides, 45 arithmetic/merge/compare boundary records, 3 mask logic,
11 gathers, 42 extension overlap, 3 kernel CSR waits and 9 segment boundaries.
The MASKU/SLDU joint simulation proves one starvation mechanism for three
restart points and their controls, NOT all 85 slide records. The 33 printed
VL512/vstart256 records contain that boundary in output; a print is not always
an exact single unreturned instruction. Twelve merge and eleven gather
records lack exact final trials. No valid-bit probe establishes that an
unqualified head-PC instruction was accepted by the backend.

Extension overlap must distinguish capture/reshuffle stalls before the target
from source-lifetime waits after issue. Kernel CSR waits must distinguish the
CSR waiting for backend idle from the earlier VLSU/fault cleanup failure.
Nine segment-boundary stalls do not establish active VL, mask or alignment;
several scenes record a preceding phase-store page fault instead.
Zero DDR outstanding counts cannot rule out an internal VLSU/token deadlock.

## Two more precise source leads

These paths were checked in the DEPLOYED archive, not substituted with the
modified working RTL. All six inspected source hashes match
`rvv_stall_archived_rtl/manifest.json` source_hashes_before_integration.

### Comparison old-destination origin

`rvv_stall_archived_rtl/lane_sequencer.sv:1066` initializes MaskB.vstart from
the ordinary per-lane vstart. Lines1090-1096 switch to packed-mask EW64 and
reset the origin only for mask-logical/carry operations, not comparisons.
`operand_requester.sv:423` adds vstart >> (EW64-eew) to the VRF word address.
At EW64, that is a direct word offset. Example: four lanes, VL8/vstart4
gives per-lane vstart1 and requests old vd starting one word too late,
although the packed destination prefix is in word0.

MASKU already protects the architectural prefix with its active-bit window
and AND merge (`masku.sv:774-785,974-980,1003-1005,1479`). Therefore simply
adding another prefix mask is insufficient if old-vd data comes from the
wrong word. This is stronger than the generic "missing prefix protection"
explanation, but internal old-vd data has not been observed on the board.
Capture MaskB vs/eew/vstart/address, returned old-vd word, iteration count,
active mask and result-queue wdata. A zero-origin control must preserve the
same original prefix. Also check alias layout; do not claim this closes all
FP comparison data errors or any exception-flag bug.

### Ordered reduction operand and exception masks use different positions

Archived `rvv_verification_handoff02/deployed_rtl/vmfpu.sv:2371-2376`
selects/compacts the current element with processed_osum_operand and
osum_element_active. For the second FP32 element those select mask[4].
But line2434 computes issue_be = be(1, EW32) & mask_i, selecting low bytes
of the unshifted mask, i.e. mask[0]'s element. With mask=0xf0 and local
element1, osum_active is true but issue_be is zero. That zero propagates to
vfpu_simd_mask/tag.flag_mask (1214-1227); the output flag gate at1507 then
suppresses NV. FP16 local element1 has the analogous mask[4] versus low-byte
disagreement. This is a concrete source-contract counterexample consistent
with the sparse opposite-infinity failure, not a new full-RTL simulation.

Capture osum_issue_cnt, incoming mask, selected operand, osum_active,
issue_be, fpnew input acceptance, output tag/status, and fflags commit.
Use opposite infinities with only a nonfirst subelement active, and a
first-subelement control. Distinguish NV never produced from NV discarded.
This candidate does NOT explain excess NV on all-off comparisons.

## Open evidence and exclusions

- The e16/m8 unmasked-v8 FP comparison's 64 data errors remain unresolved:
  both isolated and reconstructed 50-call prefix pass. Do not close the
  original or claim proven intermittent hardware failure.
- 40/41 extra comparison singles match flags; that does not cover the above
  unmatched data symptom. Old source equivalence remains a separate limit.
- NF2 has 40 matching current-oracle singles; positive/negative/zero stride
  have40/40/12. No inference that every other NF/shape is internally proven.
- RVV-01's wrong index equals adjacent 32-bit halves of intended 64-bit
  indices. EEW metadata/snapshot/replay is a candidate; exact corruption
  stage remains unknown. Resident/nonoverlap passing controls are essential.
- Original arithmetic matrix RVV-02 is retained outside the 198-record set.
- 47 mixed records are not demonstrated RTL failures: 20 memory observation
  gaps later pass exact-ELF retest; keep other mixed histories and acceptance
  limits. 124 unexecuted children have no failure result to explain.
- TEST-01..07, REF-01, observer WinError5 and loader taskkill races remain
  infrastructure/oracle/reference findings, not new RVV RTL causes.

This completes inventory/scope reconciliation and a broad candidate review.
It does NOT complete proof of every internal cause, repair acceptance, or
full-program regression. No RTL or board image was changed for this review.
