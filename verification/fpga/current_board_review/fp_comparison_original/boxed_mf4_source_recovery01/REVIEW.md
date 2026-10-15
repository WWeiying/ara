# Boxed Unmasked mf4 Source Recovery

Decision: **NOT_RECOVERED_WITHIN_BOUNDED_SEARCH**. No inspected C file matches
the historical manifest's expected hash. Related later C templates exist, but
source lineage/equivalence for this exact parent is not proven. Do not change
provenance01/parents.json to Recovered, or count this as a new accepted scope.

This parent belongs to FINAL_PENDING broader FP. It is neither the unboxed
full17920 parent nor alias17920, and does not change the current18/22 arithmetic
union. No RTL, compilation, Host, reference, DUT or large raw access occurred.

## Exact Original Identity

Name: `rvv_fp_compare_unmasked_e16_mf4`.

Archive base:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/`.

| Artifact | Relative archive path | SHA256 |
| --- | --- | --- |
| Original ELF,15648B | rvv_additions30/binaries/rvv_fp_compare_unmasked_e16_mf4 | bef54674b16fdeefdb37295d035b1b9a58cd446cd54662078aa24e83cced7b2d |
| Manifest | rvv_fp_comparisons_unmasked01/manifest.json | ec4aac5fcfe55e241472525af67c3e5c8e0feca1f791a8beb1e5829870efb8a9 |
| Assembly,3502B | rvv_fp_comparisons_unmasked01/rvv_fp_compare_unmasked_e16_mf4.S | 156cb4e726a4eb5c2c7fb267f478f0e11beb2d68aadbdbe3c0f0ef43c002988a |
| Original e16 fixtures | rvv_fp_comparisons_unmasked01/e16/fixtures.h | 5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1 |
| Original operation declarations | rvv_fp_comparisons_unmasked01/e16/operations.h | cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64 |

Expected original C SHA256:
`9060f2931a5a2b6b51e3ff7be14ce420efaeb5c34800e496dad95dd78fc89dcf`.
Expected historical generator fp_comparisons.py SHA256:
`38ec87ba8599a95a6762ed626ca6c08a31652ae96bea824522df7b4d29692cca`.
The C hash agrees between original manifest and the existing NOT_RECOVERED
parent entry, whose source inventory SHA is
`ea0d3ef9adee8426089ef547579cf57bfc6d84592cbd9fd5868b08b8b4a90e91`.

Original configuration is SEW16/mf4, UNBOXED_COMPARISONS=0,
UNMASKED_COMPARISONS=1, RESTART_COMPARISONS=0, DESTINATION_KIND=0 (v24).
Manifest says17920 configurations,32 input rotations, ten operations,
initial fflags0/1, restart=false and destination=v24. At VLEN1024, CAP is16.

The archived S independently distinguishes this case:
- Four vv comparisons and six vf comparisons target v24 without v0.t.
- Old destination and v0 are both loaded, but v0 does not predicate targets.
- Each FP16 vf scalar is loaded with LHU, then `li t3,-1; slli t3,t3,16;
  or t2,t2,t3; fmv.d.x ft0,t2`: valid NaN-boxing, not the unboxed scalar path.
- No csrw vstart,a6 appears. Capacity is e16,mf4,tu,mu. fflags are saved,
  initialized from a7, returned with vstart, then restored.

## Actual Historical Symptom

`rvv_recovery08_07/resume/board_report.json`, its terminal_scene/report.json,
and `rvv_recovery08_08/previous_report.json` all have the same SHA:
`6352fd7cf3834eff0bff08b324b5b2ac2757f442b5f9bbf9e5d06b7951e60e4c`.
They repeat one record, not three independent reproductions.

results[96] reports failed/exit1,4.750074700s, with terminal marker
`RVV_FP_COMPARE_FAIL sew=16 cases=17920 errors=1216`.
First detail is op4(vmfeq.vf),seed0,VL15,mask0,sticky0,
expected_flags0,actual_flags16,errors1. Subsequent printed records include
sticky1 expected1/actual17 and all four mask modes, plus op5(vmfne.vf)
and later op2. These are genuine original diagnostics; the bounded
first20 details do not prove every one of1216 aggregate errors has one cause.

Original `reference_1024.json` records this ELF exit0 with17920 cases/errors0.
That is historical reference evidence, not current-image DUT acceptance.

## Bounded Search And Candidate Distinction

Inspected only the named provenance, comparison parent copies, original
comparison-family directories and named recovery/additions directories, plus
the explicitly identified original generator/oracle location. No home-wide
search or large logs/traces were used. The small width_tests.tgz member listing
contains15 binaries, not C/header/generator source. Comparison-family archive
roots contain no direct *.c files; target archive retains S and generated
fixtures. Named recovery08_07/08_08/additions30 source listings yielded no C.
Path-specific git history queries for the oracle in the integration and original
source worktrees returned no tracked revision to recover.

Nine existing original/parent.c copies under the known comparison preparations
were hashed: seven have3652ca2d..., two have03cc5031..., none9060f293....
The explicit unboxed full17920 candidate is:
`../../fp_compare_unboxed_full17920_prepare01/source_model02/software/original/parent.c`.
Its4900 bytes exactly match the current canonical fp_compare_oracle.c:
`03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad`.
It is therefore the same *current later template*, not the historical target C.

The already recovered pre-unboxed template
`../provenance01/fp_compare_oracle_3652.c` has4700 bytes and SHA
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`.
Existing recovery metadata proves its exact inverse removal of two later
unboxed additions, but that proof targets3652..., not9060.... It cannot be
transferred to this earlier boxed/unmasked parent.

The current generator at the canonical diagnostic path hashes
`ae5675cb9a518a72009682bb1e55d42480d612c5badbaebc3afe445dedecde62`,
not the historical38ec87ba... generator. Its source explicitly selects boxed,
unmasked,v24,restart0 behavior using the requested definitions, but that alone
does not establish original C bytes or identical compiled scalar oracle.

In particular, the later C has restart/alias/unboxed hooks and a start>=VL
preservation rule. With original zero-valued switches some branches disappear;
without the original C or an exact binary rebuild we cannot assume all later
code simplifies to the original scalar oracle. No template substitutions or
parameter changes were made in this task.

## Optional Single Identity Rebuild, Not Executed

If separately authorized, the narrowest falsifiable next step is one Linux
identity compile using the unchanged4900B candidate03cc5031..., original S
and original e16 fixtures/operations headers, original family settings
SEW16/UNBOXED0/UNMASKED1/RESTART0/DESTINATION_KIND0, and the established Linux
cross-compiler recipe recorded in provenance01/original_rebuild.command.json.
Keep -Os/rv64gcv/lp64d/nostdlib/static/freestanding/no-vectorize/build-id-none/
stripped flags; record actual compiler identity and exact command. That existing
command proves the recipe for another family, not this earlier source revision.

Compare the sole output byte-for-byte with original ELF bef54674.... If it
matches, label **ELF_IDENTICAL_REBUILD_FROM_LATER_TEMPLATE**, while retaining
**historical_C_bytes_NOT_RECOVERED**. Do not claim that C03cc... acquired hash
9060.... If it does not match, preserve the mismatch and stop: no parameter,
oracle or compiler-flag search. Any section-level diagnosis would be static and
separately scoped. This plan is not execution permission and creates no adapter.

To prove original C recovery itself, the missing evidence remains the exact
9060... byte text, from a retained source snapshot or a uniquely documented
historical edit inversion that reproduces that exact hash. Bounded absence here
does not prove no such source exists elsewhere on the machine or off-machine.
