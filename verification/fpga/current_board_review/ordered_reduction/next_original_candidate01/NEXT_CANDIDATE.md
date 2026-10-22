# Next Candidate: Original Integer Merge Prefix98

Status: STATIC_RECOMMENDATION_ONLY. No compile, reference, DUT, service/live
query or remaining9 CSV review. No frozen/shared file was changed.

## One Recommendation

Prepare, subject to separate authorization, the **first98 natural calls of
`rvv_permute_restart_e16_m8_ops4`**, retaining all97 predecessor calls. This is
the original integer `vmerge.vvm` partition, not another gather or reduction
single. Reuse frozen M6 without an RTL build if later admitted.

At VLEN1024, cap512, the endpoint is zero-based call97:
`seed0 / op4 / scalar-slot0 / length-slot6 / mask0 / start-slot1`,
namely VL512/vstart256. The first96 calls cover all four selector patterns and
four starts at VL0,1,2,3,256,511; call96 has VL512/start1. Preserve these
duplicates and order, then stop only after call97's full original oracle.

This is **not a recovered exact historical stopped tuple**. The original
record has no final tuple or completed-call count. It is one bounded,
source-derived discriminator from a genuinely stalled program.

## Original Identity And Failure

Let `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01` and
`V=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review`.

- Original executable:
  `C/rvv_permute_partitions01/release/binaries/rvv_permute_restart_e16_m8_ops4`.
  Fresh SHA256 `275c9d872111a37c28e7466b7fbd7f263a545918315b8a98284d456950d22118`.
- Original generated files:
  `C/rvv_permute_partitions01/rvv_permute_restart_e16_m8_ops4/operations.S`
  and `operations.h`. Fresh hashes respectively
  `40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf` and
  `886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4`.
- Authentic shared C copy:
  `C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`.
  SHA `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`
  matches `rvv_permute_partitions01/manifest.json`'s source hash and the
  current `hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/permutation_oracle.c`.
  Its storage under a gather directory does not change the op4 source identity.
- Manifest SHA `6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58`:
  this child has operation_ids `[4]`, SEW16/m8, **2688** original calls.
- Actual old report:
  `C/rvv_recovery08_159/terminal_scene/report.json`, SHA
  `59de1856270eeba59d248fff0b891d47f1a776af36980ce41fb378082b154abe`.
  Result is `stalled`, empty output, "Confirmed no retirement; scene preserved".
  Two snapshots retain retired1696841672 while cycles advance564196900;
  last_pc=0x10684, head_pc=0x10688. Both DDR interfaces show zero outstanding
  transactions/error_count. These observations do not identify an internal root.
- `C/stall_family_triage02/triage.json` binds the same ELF/report, with
  `last_trial:null`, `opcode_family_candidate_no_trial`, retest `not_started`.
  The latter does not erase the earlier actual stalled report.

The original ELF's executable PT_LOAD bytes at0x10684 were read directly:
`57 0c 88 5c`, encoding `5c880c57`, `vmerge.vvm v24,v8,v16,v0`.
The archived op_4 assembly contains13 instructions: fullcap vset/load v8,
v16 and old v24; mask load; requested-VL vset; original `mv t3,a6`; vstart
write; merge; returned-vstart read; fullcap vset/store; return. A future port
must compare all13 encodings, not only this target word. No port was built here.

## Gap And Original Oracle

`CURRENT_SCOPE.md` still leaves original arithmetic/merge/compare45 open.
The prior `arithmetic_restart_original/NEXT_ORIGINAL_SCOPE.md` identifies
**12 integer-merge records without final tuples**, distinct from33 records
with a printed VL512/start256 boundary. This child is one of those12.
The reviewed current Markdown inventory contains no accepted source-faithful
op4 sequence for it; this is a bounded evidence search, not proof no private
experiment exists.

Preserve original RNG seed/state, ordinary `indices` (a1, not indices16), all
initialization, all128 mask bytes and all512 destination halfwords per call.
Within `[vstart,VL)`, the original oracle selects `indices[i]` when v0[i]=1,
otherwise `input[i]`. Outside that range it requires old0x005b. **A zero
selector is not a masked-off write**: do not reuse gather's inactive-element
oracle. No index/OOR rule applies to these merge data values. Scalar-slot0
and `mv t3,a6` remain present even though this vv target does not use t3.

Required totals:98 targets,98 ordered13-instruction windows,50176 result
halfwords,196 guard halfwords,98 returned-vstart checks. Retain original
errors/DETAIL veto, final original PASS/exit, full prestart/tail preservation
and guard checks. No new arithmetic/fflags oracle is invented: this source
checks returned vstart, data and guards. Full-capacity source setup and original
CSR instructions remain mandatory even for VL0 or vstart>=VL.

This adds large-group **integer selector-stream** behavior with both vector
sources, unlike accepted gather prefixes and FP scalar merge. Existing
`fp_merge_original/candidate04_run01/complete.json` already reports its195-call
`vfmerge.vfm` prefix PASS4782.17s; do not repeat that as this new work.
The fixed/macc single+pair results likewise do not cover integer merge.

## Firmware And Time Evidence

No firmware count for this new op4 prefix has been measured. The closest
existing measured proxy is the same shared C, SEW16/m8, cap512,98 calls and
full50176+196 oracle in:
`V/gather_original_review/e16_m8_ops1_prefix98_terminal_audit01/REVIEW.md`.
It independently accepts M6 gather-vx with1997782 SoC retirements,
last cycle2980012 and2980.8859622 simulator seconds, approximately670.20
retirements/s. Its existing reference reports2002820 retirements. These are
historical recorded measurements, not a fresh CSV scan or live observation.

For planning only, use approximately **2.0..2.5M firmware instructions**:
the same per-call initialization/full-capacity scalar loops dominate, while
op4 changes active result selection and vector execution. The upper end is
a25% planning allowance, **not a proven static bound or a compiled count**.
At that measured M6 proxy rate, plus20% wall-time allowance, this implies
3581..4476 seconds (about60..75min). Thus one9000s case/10200s service is a
reasonable future admission envelope, not a launch recommendation today.

At the older adverse273 retirements/s proxy the same range plus20% becomes
8791..10989s; the upper estimate exceeds both9000s and3h. Budget feasibility
therefore depends on obtaining the actual unchanged-source reference count
and accepting the measured same-shape M6 throughput proxy. Do not promise
completion, increase limits automatically, shorten the oracle or retry if it
does not fit. A later software-only preparation must resolve this uncertainty
before DUT admission. No such reference is authorized/executed by this note.

The held FP-compare682 prefix is20.260M reference retirements and an estimated
8.02..8.08h from its measured controls (`fp_comparison_original/TERMINAL08.md`),
so it is not the preferred bounded next item. This recommendation is one
98-call sequence, not another large batch or a request to run full2688.

## Accounting Boundary

Parent now reports remaining9 reduction singles complete9PASS; Aquinas owns
their independent audit. This note does not reread their CSV or upgrade that
parent observation into an independent acceptance. `CURRENT_SCOPE` and the
original11 inventory's old pending language are historical at this point.
Together with accepted e16/mf4 and reused e32/m1, those9 address the11 reduced
source singles, **not11 full6720-call reduction parents**.

The proposed98 belong to exactly one original merge partition. They are not
an exact historical failing tuple, the entire2688-call partition, the combined
unpartitioned permutation parent, Linux/board replay, all12 merge records or
all45 stalls. Integration38/48, compare19/19, arithmetic-prefix5 and module
matrices remain separate acceptance scopes. Even a future prefix PASS cannot
close the original unknown-stop record; it would establish only this exact
original-source prefix on its pinned current image.
