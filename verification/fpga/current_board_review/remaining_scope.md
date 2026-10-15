# Remaining Historical Failure Scope

> Historical inventory, not the latest acceptance ledger. Subsequent comparison,
> extension, slide and masked-memory repairs supersede several pending statements
> below. Consult `README.md` and each hash-bound campaign report for current
> results. The family/provenance inventory remains useful; its original status
> claims are deliberately retained as a dated audit rather than silently rewritten.

Static sidecar, 2026-10-10. No new RTL edits, simulations, builds, board runs,
or closure claims. The root README and accepted gather RTL/pins are unchanged.
Line references below are to the inspected integration worktree, not to an
assumed identical FPGA mirror. Existing test results are attributed to their
owners; this audit did not rerun them.

## Bounded Closeout

Parent-reported checkpoint received after the static audit: final-RTL unit
matrix **3648 PASS**, full image built, **four original-source ports PASS**;
the remaining two source-level filter-loop slow cases have fast software
prepared, with **14 Spike checks PASS**, retaining the same image. These
are parent-reported results, not additional executions or independently
rehashed artifacts from this sidecar. Spike success is not an RTL execution
result for those two cases. The four passing ports are not mapped to exact
ELF identities here; the parent's integration evidence owns that mapping.
Earlier per-family "pending" entries below mean closure is not established
by this static audit, not that the parent has run no original-source ports.

Untouched or unclosed mechanisms must remain distinct:

- **Comparison excess NV:** no comparison predicate/exception repair found
  in the inspected deployed/current diff. All-off, tail and prestart leads
  remain static hypotheses; old-vd and reduction fixes do not close them.
- **Nonindexed masked translation:** no predicate-suppression repair found.
  Existing FOF forwarding/terminal-marker and VLDU retirement changes address
  different contracts. Protected-page, signal/replay and kernel-cleanup
  findings still require their real system environment for acceptance.
- **Extension overlap:** classifier/reshuffle/dependency candidates remain
  unproven; the precise blocked state is unknown. Retain the measured VL127
  setup, not the passing VL2 generic case. No new extension fix is claimed.
- **Other residuals:** large-offset/sequence-dependent slide behavior,
  unmapped gather stalls, indexed NF7 check identity, indexed overlap replay,
  and segment/kernel boundaries retain the evidence limits in the inventory.
  Mixed/unexecuted records and setup/oracle exclusions are not new RTL bugs.

This closes the bounded inventory only. No scope expansion, tests, simulation,
RTL/pin edits, or root-README edits were performed for this checkpoint.

## Evidence Roots and Status Vocabulary

- `I` = `/home/wangwy/openproject/ara_dsa_signoff_integration`.
- `C` = `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
- `R` = `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`.
- Scope authority: `R/repro/ALL_FAILURE_REVIEW.md`, `R/repro/STALL_TRIAGE.md`,
  `R/ISSUES.md`; identity reconciliation: `C/all_failure_scope_audit02/audit.json`.
- `D` = `C/rvv_verification_handoff02/deployed_rtl`. The deployed source
  binding is `C/rvv_stall_archived_rtl/manifest.json`, field
  `source_hashes_before_integration`.
- **Local fix present** means the particular source mechanism was changed,
  not that its original Linux ELF passed. **Plausible** means a falsifiable
  current-source defect candidate, not a new measured failure. **Linux** means
  preserve page permissions/traps/replay/kernel behavior for historical closure.
  **Evidence gap** is neither a pass nor permission to invent a trigger.

The 871 failed, 198 stalled, 47 mixed and 124 unexecuted entries are ELF
records, not independent bugs. Original/partition records overlap. This
sidecar accounts for every family in ALL_FAILURE_REVIEW, not every inner trial.

## Remaining-Family Inventory

| Historical family / records | Current disposition | Next boundary and provenance |
|---|---|---|
| RVV-03 whole move / 2 failed | Local fix present, parent integration | Dispatcher request geometry repaired; do not reopen here or infer full VRF numerical closure. `dispatcher/results.json`. |
| RVV-05 widening FP reduction / 1 failed | Local fix present, parent integration | m8 legality fixed; nonzero-VL arithmetic acceptance remains separate. `dispatcher/results.json`. |
| RVV-07 ordered sparse reduction / 11 failed | Local fix present, parent integration | Selected-element exception mask corrected; not RVV-09. `ordered_reduction/MEASURED_20261010.md`. |
| RVV-19 gather numerical / 83 failed | Local fix present, parent integration | BE prestart guard passed focused unit; genuine vv source replay remains separate from generic vx fixture. `gather/README.md`. |
| RVV-09 nonrestart comparisons / 208 failed | Plausible, highest-priority arithmetic follow-up | All-off predicate, unmasked tail NV, and data errors are separate subcases. Section below. |
| RVV-09/11 FP comparison restart / 29 failed | Partial local fixes; flags still plausible | Old-vd origin and long mask supply have focused repairs; exception mask/restart coordinates still need investigation. Keep e16/m8 unmasked-v8 64-data-error original unresolved: isolated and 50-call reconstructed prefix pass (`C/rvv_compare_prefix_board232_01.json`). |
| RVV-12 scalar compare restart / 19 failed | Local origin fix, original acceptance pending | Current `lane_sequencer.sv:1104` requests packed old vd from zero, unlike deployed ordinary lane vstart. `lane/README.md`; not proof all numerical/stall records closed. |
| RVV-13 aliased compare restart / 19 failed | Partial origin fix; alias/layout evidence gap | Same old-vd fix, but mixed-layout/source lifetime and allowed agnostic bits remain distinct. `R/ISSUES.md` RVV-13 and TEST-06; retain exact oracle. |
| RVV-10 FP moves/slides / 49 failed | Partial parent slide repair; original sequences pending | 47 matching numerical partitions are not all the same prefix/insert/completion problem. Source `C/rvv_move_symptoms02/symptoms.json`; preserve mixed stored EEW and operation sequence. |
| RVV-08 large-offset slideup / 3 failed | Plausible sequence/mask-position issue | Current restart repairs are not proof for vstart0 offset=VLMAX-1. e8/m4 VL512/offset511 gets old91 with all-on, source185 with all-off/sparse. `C/rvv_recovery08_07/resume/board_report_live02.json`; e16/m8 in live03. Check `masku.sv:1745,1793` stride/pointer and SLDU consumer, retaining sparse/all-off preceding calls. |
| RVV-04 protected-page/FOF / 8 failed | Plausible nonindexed suppression; partial FOF fixes; Linux | Section below. Do not combine five failing scenarios or ordinary/FOF loads into one cause. |
| Unit/strided/segmented replay / 429 failed | Linux; subset has same suppression candidate | Keep NF1/NF2, positive/negative/zero stride, field boundaries, metadata/data/guard checks separate. `C/rvv_fault_batch_handoff01`, `rvv_fault_handoff64_01`, `rvv_segment_fault_handoff01`, `rvv_strided_fault_handoff01`, `rvv_negative_stride_handoff01`, `rvv_zero_stride_handoff01`. Singles reconstructed with current oracle do not prove original per-trial equivalence. |
| RVV-15 indexed NF7 / 1 failed | Linux + missing failing-check identity | `rvv_fault_replay_segment_nf7_indexed_e32_mf2`, SHA256 `581a695b625716256771c14df272b7afa912b1fa55f6180822d5bc7d17c87b42`; `C/rvv_recovery12_indexed_failure01`. 96 cases/72 signals/one check error, disjoint groups. Indexed predicate skip already existed; cannot substitute unit stride or infer the check. |
| CAP-01 preparation / 9 failed | Capability/setup, not target segment proof | `C/rvv_segment_setup_audit01`, `rvv_segment_setup_single01`; SIGBUS on ordinary nonaligned preparation load before target. Separate from nine segment stalls. |
| Slides / 85 stalled | Parent focused mechanism repaired, per-record gaps remain | Three joint starvation repros and later matrices do not certify all 85 original sequences. `STALL_TRIAGE.md` A, current slide/lane evidence. |
| Arithmetic/merge/compare boundary / 45 stalled | Local mask-stream fix; original acceptance pending | Current `lane_sequencer.sv:1223` restores zero-origin full mask stream for ALU/MFPU/MASKU. 33 printed VL512/start256 records versus 12 merges without exact final trial. `STALL_TRIAGE.md` B. |
| Mask logic alias / 3 stalled | Local source-stream fix; alias sequence pending | Current `lane_sequencer.sv:1224` exempts mask-logical source from predicate trimming. `masku.sv:796` also changed same-register identities. Neither alone proves original completion. `STALL_TRIAGE.md` C. |
| Gather / 11 stalled | Evidence gap, independent of accepted BE fix | Current mask-stream repair is relevant. Out-of-range/no-data handling (`masku.sv:1365,1455,1542`) already exists in deployed archive too; it is NOT a new current fix versus that baseline. Recover exact final trial and distinguish mask starvation from request/data tokens. `STALL_TRIAGE.md` D. |
| Extension overlap / 42 stalled | Plausible classifier/maintenance/dependency issue | Exact VL127 single exists; VL2 generic passes and is not a reproducer. Section below. |
| Kernel vector CSR / 3 stalled | Linux; internal unit unknown | `R/ISSUES.md` RVV-16; `C/rvv_recovery08_12/terminal_scene`, `zero_stride_stall_annotation.json`. Current `ara_dispatcher.sv:1237,4650` still waits for idle before flush/CSR. A stopped unqualified PC is not a valid accepted CSR request. |
| Segment boundary / 9 stalled | Linux + acceptance gap | `R/ISSUES.md` RVV-18; `STALL_TRIAGE.md` G. Preserve scalar phase-store fault, segment target, translation response and field completion separately; active VL/mask may be unknown. |
| Supplemental RVV-01 indexed overlap/fault | Linux; exact corruption stage unknown | `C/HARDWARE_FINDINGS.md`, `width_fault_timeout02.json`, `campaign03_fault_evidence.json`, `width_restart04_live.json`. Wrong index comprises adjacent 32-bit halves; current dispatcher snapshot path at `ara_dispatcher.sv:5393` already existed deployed. Retain resident/nonoverlap controls. |
| Supplemental RVV-02 arithmetic restart | Local mask-stream fix; parent original replay | Original 22-shape matrix outside the 198-record inventory; do not count it twice. `R/ISSUES.md:19`, current lane mask-stream evidence. |
| 47 mixed / 124 unexecuted / TEST-01..07 / REF-01 | Excluded from automatic RTL attribution | 20 observation gaps later pass exact-ELF retest; others retain mixed history. Unexecuted children have no failure to explain. Handler/oracle/observer/reference problems remain separate. |

## FP Comparison Excess NV

### Original testcase and limits

`R/ISSUES.md:2794` binds original `rvv_fp_compare_e16_mf4` to additions28
and `C/rvv_recovery08_07/resume/board_report_live07.json`: op0 `vmfeq.vv`,
seed0, VL8, mask mode3 (all off), sticky0, expected0/actual16. Sticky1 gives17,
not1. Source v16 element5 is sNaN0x7c55. FP32/64 observations are in live08.
The original ELF hash is
`777190b9d2ea291329db61a01bee011ae389280d30c1437d9ad64901ad46d15f`.

Usable reduced source is
`C/rvv_small_fp_compare_reconstructed01/rvv_small_fp_compare_e16_mf4/`.
Its binary SHA256 was rechecked here:
`96aaa86168ddcb6df8c5d931e6582975cc93ad42dc62c0fa8baeba2bba583345`.
`scenario.S:9` saves flags; lines16/17/19 write sticky flags, execute the
target, then read flags before destination readback. The manifest explicitly
says `oracle_provenance=current_reconstruction`, with changed original C
oracle/generator and archived assembly. `C/rvv_reduced_symptoms04/symptoms.json`
confirms the flag symptom, explicitly NOT vector-data equivalence or cause.

### Current versus deployed

1. `I/hardware/src/lane/vmfpu.sv:2663` forces vm=1 for VMFEQ..VMFGE at
   admission; deployed `D/vmfpu.sv:2648` is identical. Data predication is
   delegated to MASKU, but exceptions are produced in VMFPU.
2. `vmfpu.sv:1831` gates issue BE by local count, restart only for VFU_MFpu,
   and queued vm/predicate. Forced vm=1 defeats all-off filtering. Comparisons
   are VFU_MaskUnit, so the ordinary restart gate is also bypassed. This block
   is unchanged deployed/current, not affected by the ordered-reduction repair.
3. `vmfpu.sv:1214,1227` maps BE to SIMD mask and carries flag_mask in the tag.
   `hardware/deps/fpnew/src/fpnew_noncomp.sv:261` produces NV on sNaN;
   `fpnew_opgroup_fmt_slice.sv:309` masks each lane status before OR.
   `vmfpu.sv:1507,1545` gates aggregate flags by tag-mask nonzero and registers
   accepted output flags. Thus masking EXISTS, but the comparison execution
   mask is not the architectural predicate. Simply adding another aggregate
   OR-mask gate cannot restore information discarded upstream.
4. A separate tail counterexample: `lane_sequencer.sv:428` rounds MASKU
   preprocessing VL up on EVERY lane when global VL is not divisible by four.
   Global VL15 gives local VL4 even on lane3, allowing element15 into flags.
   This matches the independent unmasked-vf tail-sNaN observation at
   `R/ISSUES.md:2822` (live10), but is still static, not a captured current run.
5. Do not flip queued vm alone: `hardware/src/lane/lane.sv:216,240` routes
   VFU_MaskUnit mask beats to the ALU side, not MFPU. Repair ownership includes
   mask delivery/consumption and balanced comparison results, not just one flag.

**Next discriminating work, not run:** original all-off e16/mf4 fixture with
active-sNaN and no-sNaN controls; separately unmasked VL15/tail-sNaN and a
restart-prefix sNaN. Observe accepted VFU vm/vl/vstart, routed mask beats,
issue BE, FPnew input handshake/SIMD mask, returned tag/raw status, registered
lane flags and CSR sticky result. If NV originates before target acceptance,
or flags commit with an unrelated tag, distinguish that from this mask loss.
No Linux protection mechanism is needed for the isolated arithmetic fixture.

## Masked VLSU Translation and FOF

### Original testcase and limits

`C/rvv_small_exceptions01/manifest.json` records byte-identical original
rebuilds. Focused e16 scenario3 is VL8/all-off ordinary `vle16.v` at PROT_NONE;
the original `rvv_exceptions_detail_e16` SHA256 is
`d7f8507da5afaf4c4683bb5b35861f6f99cd71bcbf06f6622a791d9786c55923`.
The single binary hash was rechecked:
`9de2343469ad5bd8d5c7ac817bed69ba2d9847bc29f2426a6b817f343b08651c`.
Sources: `C/rvv_small_exceptions01/rvv_small_exceptions_e16_scenario3/`;
`scenario.c:34` selects scenario3, line37 makes mask zero, line40 chooses
the protected page; `scenario.S:12` is the masked target after staging vd/v0.
`C/rvv_exception_symptoms02/symptoms.json` matches original/single cause13,
SIGSEGV11 and page offset0; single PC0x10458 opcode00055c07. This is a real
permission failure, not a returned-output mismatch or generic load timeout.

Scenarios0/1/2/3/5 must stay separate: active-prefix FOF shortening,
masked cross-page ordinary/FOF loads, and all-off ordinary/FOF loads.
Scenario4 is the intentional first-element fault control. The 429 replay
records additionally include stores/handlers and segment/stride interactions.
The positive-stride NF8/e32/mf2 169-error outlier must not be flattened into
the common128-error cases (`R/ISSUES.md:458`).

### Current versus deployed

- **Still plausible:** `hardware/src/vlsu/addrgen.sv:620` only consults
  predicate owner/position in ADDRGEN_IDX_OP. Lines920/939 implement indexed
  skip/active gating; for nonindexed state, the start-request condition
  bypasses predicate checks. Lines1135/1137 then assert translation and
  lines1213/1234 propagate its exception. These blocks are unchanged from D.
  Masking load writeback or store strobes later cannot prevent that fault.
- **Already present, not newly fixed:** indexed inactive-element skip tokens
  at lines920..938 existed deployed. Do not ascribe NF7 indexed errors to
  missing nonindexed predication, nor assume presence proves the whole indexed
  pipeline correct under replay.
- **Actual intervening FOF repairs:** deployed `ara_sequencer.sv:793` omitted
  fault_only_first in the PE request; current `hardware/src/ara_sequencer.sv:796`
  forwards it. Deployed `D/addrgen.sv:1232` suppressed the internal exception
  marker for nonfirst FOF faults; current `addrgen.sv:1234` always enqueues it
  to terminate VLDU, while `ara_dispatcher.sv:4363` separately suppresses the
  architectural trap and sets VL. These are existing changes, not evidence
  that all original FOF cases now pass.
- **Actual intervening VLDU repair:** current `hardware/src/vlsu/vldu.sv:481`
  retires a descriptor only after consuming its final beat, comparing the
  current beat index and supporting skip retirement without RVALID. The
  hash-matched deployed version used a wrapping next-count comparison outside
  that consumption block. See `verification/patches/README.md` for the owner's
  bounded burst checks; they do not establish Linux fault/replay closure.
- **Cleanup still needs discrimination:** `ara_dispatcher.sv:1237` waits for
  ara_idle before starting flush; the system-CSR path at4650 waits for idle.
  Capture exception/ack, pending load/store/segment tokens, mask ownership,
  flush state, backend running IDs, and CSR request VALID, not just head PC.

**Next work, not run:** begin with the genuine scenario3 and scenario4 control,
preserving virtual translation, PROT_NONE and child signal handling. A focused
MMU-response model can establish whether inactive elements request translation,
but cannot close original Linux signal/replay findings. Then isolate FOF
scenario0 with the now-forwarded FOF bit and terminal marker; only afterwards
expand to stride sign/zero, segment fields and signal-handler replay.

## Extension High-End Overlap

### Original testcase and limits

`C/rvv_extension_symptoms01/symptoms.json` binds original204, trace211 and
single213. Original `rvv_extension_e16_m2_vf2` SHA256:
`64a3b5ff90e9a7d2cb2b086b5f9a8b373b67ab95cf87ec3843fe42b99dc5d965`.
Rechecked single SHA256:
`46e4a83a8ee93456229cfdd04acb9cb0e3d31dcd67d62a7af8af2f503f4cf9e5`.
`C/rvv_extension_single01/rvv_trace_extension_single_e16_m2_vf2/scenario.S`
op2 retains `vl2re8.v v24`, e8/m1 load of v25, v0 load, e16/m2 configuration,
then `vzext.vf2 v24,v25,v0.t`. Destination starts as0x5b; source byte i is
`((i*73)^0x85)&255`. Measured trace/single tuple is seed0/op2/VL127/mask0,
cap128, VLEN1024, tu/mu, vstart0. Single cycles advanced583823180 with
retired1688870403 unchanged at vsetvli/extension boundary. The original did
not print VL, and head-valid was unavailable: do not promote this to an
observed accepted extension or proof of identical original inner trigger.
Generic VL2 passed recovery209 and is not the stalled reproduction.

### More precise current static candidate

`ara_dispatcher.sv:1205` initializes destination vtype from CSR. VXUNARY0 at
2809 decodes extension as VADD+zero; VF2 at2864 lowers source EEW/LMUL and
sets CVT_WIDE, but does NOT raise destination SEW above CSR SEW.
`legal_widen_overlap` at5668 nevertheless requires
`ara_req.vtype.vsew > csr_vtype_q.vsew`. Thus this extension cannot satisfy
that classifier merely by setting CVT_WIDE. This exact gate exists deployed
at `D/ara_dispatcher.sv:5631`; deployed VF2 decode is at2847.

For the mixed-layout setup, destination normalization request at
`ara_dispatcher.sv:5375` can therefore follow ordinary `prepare_reshuffle`
at5788 rather than the widening overlap repair path at5790. This is a
concrete classifier mismatch to test, NOT proof it caused the historical
stall or that a particular source word was corrupted. In particular, the
earlier broad OVERLAP_WAIT_ORIGINAL hypothesis must first prove that the
instruction actually entered that state.

Other retained alternatives: overlap capture waits for idle at1334/1368;
original completion waits for accepted request plus idle at1381; sequencer
WAR/source lifetime classification at `ara_sequencer.sv:699` and requester
stall terms at `lane/operand_requester.sv:496` can block consumption. The
requester is byte-identical deployed/current; sequencer's only deployed/current
diff is FOF forwarding, not an extension hazard fix. Dispatcher overlap blocks
are unchanged across the reviewed diff. Existing slide maintenance datapath
repairs could affect reachability, so current failure must still be measured.

**Next work, not run:** preserve the exact VL127 setup in a bounded full-Ara
replay, with ordinary nonoverlap and known-passing VL2 controls. First observe
decode EEWs/EMUL, classifier, reshuffle request bits, maintenance state and
valid/ready acceptance; then per-ID hazard/lifetime/operand progress and done.
An original-not-issued stall, accepted-target dependency stall, and post-target
fixup stall require different explanations. Linux is not intrinsically needed
for this extracted arithmetic/setup stimulus; real request/VRF maintenance is.

## Source Identity Checkpoint

Recomputed hashes below match the manifest for deployed files. Suffix paths
are relative to `I/hardware/src`, except FPnew under `I/hardware/deps/fpnew/src`.
Current hashes are a point-in-time audit, not a replacement for parent pins.

| File | Deployed SHA256 | Current SHA256 |
|---|---|---|
| lane/vmfpu.sv | `1f8288ed2a50f8fa59a7ea3d6f3a7e3138f5219bbb1af52e864d9dfe359d8307` | `93a0222788d3d6e740d88722e4533ad5710199594788a83a597f7a7d65487b0d` |
| vlsu/addrgen.sv | `abbdabe6a9d13cc81ad27ffa38f0149ec9c8f9f3b0383bf142b7d9987da5d2ac` | `a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988` |
| ara_dispatcher.sv | `9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43` | `4eda3df195e1a8ec319e51a14df1a051964cd08f6ee10335145a7c10cc89db4d` |
| ara_sequencer.sv | `acf333e10d5b143cddb5bf037e55067bde4f3d644cb01ea4a8e82525c0f97454` | `601165e265b57fe8a42188e1f7d9c7bbcaa78b6c21f65c6fad09d0837563da2f` |
| lane/operand_requester.sv | `327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2` | same |
| vlsu/vldu.sv | `2661d1d5bd22ad95825c38be679622d7bae987deae743e12d1fadfe7c3b0af0d` | `5700da41de5b85998b3feba441a4bddda0645b4f0f00f04927baedeb0899f07c` |
| vlsu/vstu.sv | `139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2` | same |
| fpnew_noncomp.sv | `a808cb6c09532488d2b9f41340f4d09b56e4a1c8dc113d169389d733b349e4b0` | same |
| fpnew_opgroup_fmt_slice.sv | `c6819beb6a21ae10e12a3529d4e315dba4447b40f088c9c0a70775cf089d08b8` | same |

VMFPU/AddrGen/dispatcher came from D; requester from
`C/rvv_stall_archived_rtl`. Deployed sequencer/VLDU were read from
`/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/`
ONLY after their hashes matched the deployed manifest. The integration
worktree's FPGA mirrors do NOT match those hashes and were not substituted.
Unchanged FPnew/VSTU claims use current-file hashes equal to manifest entries.
The VMFPU delta is reduction-specific; AddrGen delta is the FOF marker;
sequencer delta is FOF forwarding; VLDU delta is beat retirement. None is a
comparison predicate repair or nonindexed translation suppression repair.

## Handoff Order

1. FP comparison all-off flag path: compact, source-grounded hypothesis with
   genuine fixture and no Linux dependency. Keep tail/prestart subcases separate.
2. Extension VL127: test classifier/maintenance reachability before changing
   hazard rules. Do not substitute a direct VFU test or the VL2 passing fixture.
3. Protected-page scenario3 plus FOF scenario0: reserve real translation and
   Linux replay acceptance; first distinguish unchanged suppression from the
   existing FOF fixes. Broaden only from a measured discriminating result.

No new test, RTL change, or additional campaign is authorized by this inventory.
