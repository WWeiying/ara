# Remaining Original Scope

2026-10-14. Sole verification worktree:
`/home/wangwy/openproject/ara_dsa_signoff_integration`.
Read-only source, metadata and selected identity hashes; no simulation, reference
execution, Host run, build, RTL change or closed-CSV traversal. Only this report
is new. Relative paths below are from `verification/fpga/current_board_review`.

## Findings

1. RVV-02 original arithmetic restart22 is NOT accepted by full777 or MACC482.
   Their actual terminals are `fixed_restart_original/full777_optimized_prepare01/vcs_m8_run01/complete.json`
   (`PASS_CONTINUOUS_FULL777_M8`) and
   `arithmetic_restart_original/macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/prepared01/complete.json`
   (`PASS_FULL482_M8_ARCHITECTURAL_NOT_LINUX`). These are separate source identities,
   loops and helper/oracle contracts, not the rvv_extended04 arithmetic22 suite.
2. Arithmetic22 has FOUR complete accepted cap16 shapes, not zero or two:
   e8/mf8, e16/mf4, e32/mf2 on M6; e64/m1 on M7. They total20160 original calls,
   322560 results and40320 guards. E64's -O2 scalar derivative does not shorten
   original order/helpers/oracle. None establishes original Linux execution.
3. Whole-register20 partitions/1134 tuples and the missing59 adjacency supplement
   are accepted on M4. Do not rerun or prepare those as pending. Their union is
   NOT one continuous1134-call original-history execution.
4. FP16/m8 unmasked-v8 call50 is already included in accepted first50 on M6 and
   first682 on M8. The original64-error symptom did not recur in those scopes.
   Do not report first682 as pending. Full17920 original parent remains open;
   no historical root-cause or Linux closure follows from prefix PASS.

## Accepted Authorities

- E8: `arithmetic_restart_original/full_small2_e8_offline_recovery_audit01/run01/TERMINAL.json`,
  `INDEPENDENT_E8_FULL_ORIGINAL_OFFLINE_RECOVERY_ACCEPTED`.
- E16: `arithmetic_restart_original/full_e16_mf4_terminal_audit01/run01/TERMINAL.json`,
  `INDEPENDENT_FULL_E16_MF4_TERMINAL_ACCEPTED`.
- E32: `arithmetic_restart_original/full_e32_mf2_terminal_audit01/run01/TERMINAL.json`,
  `INDEPENDENT_FULL_E32_MF2_TERMINAL_ACCEPTED`.
- E64: `arithmetic_restart_original/full_e64_m1_o2_vcs_m7_plan01/prepared01/complete.json`,
  `PASS_M7_FULL_ORIGINAL_E64_M1_5985_CALLS_NOT_LINUX`.
- Arithmetic five prefixes: `arithmetic_restart_original/TERMINAL_AUDIT01.md`
  and `candidate04_plan01/complete.json`: e8/m2,m4,m8 and e16/m4,m8,262 calls total.
- Whole partitions: `whole_register_original/strict_acceptance01.json`,
  `WHOLE1134_STRICT_TERMINAL_PASS`, validated by `strict_acceptance01_validation.json`
  and `terminal_audit01.json`.
- Whole59: `whole_register_history_edges/terminal_resume20261011.md` and
  `successor02/preflight01/complete.json`:59 fresh pairs,118 executions,117 exclusions.
- FP682: `fp_comparison_original/full682_vcs_m8_plan01/prepared01/complete.json`,
  `PASS_M8_ORIGINAL_ALIAS682_NOT_FULL17920_OR_LINUX`; actual monitor receipt
  `prepared01/replay/tests/alias_v8_e16m8_prefix682/child_outcome.unvalidated.json`
  is integer0/4259.165035946295s, no timeout/failure. `strict_original.json`
  accepts682 calls,349184 bits,1364 guards,682 flags/vstarts,12592 helper instructions.

CURRENT_SCOPE's newer acceptance sections supersede its old rows U/FP682-pending
and the older family README snapshots. `full22_remaining_inventory01/REVIEW.md`
also predates e16/mf4 and e64/m1 acceptance. These old documents were not edited.

## Arithmetic Remaining And Next Preparation

18 complete shapes remain: e8/{mf4,mf2,m1,m2,m4,m8},
e16/{mf2,m1,m2,m4,m8}, e32/{m1,m2,m4,m8}, e64/{m2,m4,m8}.
They contain86940 original call positions. Subtracting the accepted262 M4 prefix
positions leaves86678 outside either scope; that mixed-image accounting is not
current-image whole22 acceptance. Original stalled e8/m4,e8/m8,e16/m8 still lack
full4095-call acceptance. A different small control must not replace these failures.

**Smallest useful next complete preparation: original rvv_matrix_e8_mf4.**
Cap32,25 integer operations,3 seeds,4095 calls,131040 result elements,
8190 guard elements,4095 vstarts and53235 original helper instructions.
Lengths are0,1,2,3,16,31,32, with original modes and starts including duplicate
zero positions; do not deduplicate. Original arrays a/b1024, out1026 and physical
mask128B stay intact. Full output per call is32+2 bytes, not old cap16+2.

Exact available inputs, freshly hashed:

- Source/oracle: `arithmetic_restart_original/recovery22/reconstructed_oracle.c`,
  SHA `7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.
  It is binary-equivalent reconstruction, NOT recovered original C bytes.
- Identity proof: `arithmetic_restart_original/recovery22/report.json`, all22
  exact_elf_equal/disassembly_equal; candidate membership in
  `full22_remaining_inventory01/inventory.json`.
- Rebuilt Linux ELF: `arithmetic_restart_original/recovery22/rvv_matrix_e8_mf4`.
- Original ELF: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04/overlay/opt/ara-tests/rvv_matrix_e8_mf4`.
  Both SHA `da5d08b60f2b68567aea7254fc3c3ab1ce8c14369e5f473b384fa91248fce823`.
- Original assembly: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04/rvv_matrix_e8_mf4.S`,
  SHA `2216c7663efc94db8dd0a663cf4be32b55eac8b8bdb682c04adc445045e96b5c`.
- Header: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04/e8/operations.h`,
  SHA `7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c`.

Executable next work is a fresh source-faithful cap32 SoC/Spike adapter and
independent oracle/Host/cost measurement, not another inventory or simulation now.
Reuse mature runtime/numeric/pin/checker mechanisms, but do NOT invoke the sealed
cap16 prepare/model unchanged: `full_small2_prepare01/model.py` hardcodes CAP16,
lengths8/15/16 and old output sizes; `prepare.py` hardcodes marker/Host out16.
Reset-GPR recovery is restricted to the old e8mf8 identity. Bind this candidate's
actual capacity/helper machine code and derive its own PCs and ABI/reset profile.
Original source has no explicit fflags assertion; do not claim one.
No full cap32 SoC READY or own measured firmware cost was found. Source-ready is
not launch-ready, and no <=3h estimate is established for this shape yet.

## Whole-Register Exact Remaining

Only the continuous original-history source port,1134 calls/366 exclusions,
remains within this detailed matrix. Existing executable:
`whole_register_original/prepared01/soc/whole_all.elf`, freshly verified SHA
`1bc25e3b43097c0611fc3307a157460eae1552d4eecef609a795b76073e4a925`.
Source/oracle/helper: `prepared01/original/whole_oracle.c`, `whole.S`, `whole.py`;
runtime delta: `prepared01/wrapper.diff`; ordered membership: `prepared01/tuples.json`;
manifest: `prepared01/soc/programs.json`; continuous reference:
`prepared01/complete.json` and `prepared01/spike/whole_all.elf`.

`whole_register_original/WHOLE_CONTINUOUS_HISTORY_PLAN.md` describes exact1133
adjacencies. Whole59 proves local boundaries, not all preceding state. Do not
substitute pairs or another partition for continuous history. Existing partition
measurements sum37633.854s serial for27209016 retirements; full reference records
33497309 retirements. Parallel7423.802s campaign elapsed cannot be a serial full
budget. This is genuine executable source but not a safe short launch: next work
is a reviewed continuous checker/software-cost feasibility plan, no automatic
long service or budget extension. Original Linux ELF closure remains separate.

## FP Parent And Smallest New Historical Boundary

Parent identity: `rvv_fp_compare_unmasked_alias_v8_e16_m8`, NOT a restart variant.
Actual defines SEW16,UNMASKED1,RESTART0,UNBOXED0,DESTINATION_KIND1; cap512.
The retained call50 tuple is op0/seed0/VL512/mode0/sticky1, flags17/17/errors64.
Equal flags do not by themselves prove all64 were data errors (guard/vstart
checks also contribute); existing reports' at-least62 bound is retained.

Material root: `fp_comparison_original/prepared02/prepared/alias_v8_e16m8_prefix682/`.
`original/parent.c` is the recovered exact C SHA
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`.
`original/scenario.S`, `operations.h`, `fixtures.h` preserve helper/input/oracle.
`original_rebuilt.elf` matches original SHA
`266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
Original ELF: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8`.
Proof/context: `provenance01/parents.json`, `provenance01/original_rebuild.json`,
`ready_audit01/original_contexts.json`; original assembly is in campaign
`rvv_fp_comparisons_unmasked_alias_v8_01/`.

Full original17920 scope is32 seeds*10 ops*7 lengths*4 modes*2 sticky settings;
remaining call positions683..17920 total17238. Preserve full64B mask output,
two guards, exact active/prestart/inactive/tail allowed sets, flags and vstart.
Tail allows old bit,1,or fixture result according to original policy; not blanket
ones or exact-only substitution. No fresh full-parent SoC READY was found.

If bounded original-failure expansion is preferred over a full-parent attempt,
the next retained historical failure is **call683**, not an invented new case:
seed1/op2/VL1/mode1/sticky0, expected_flags0/actual16/errors1 in
`ready_audit01/original_contexts.json` for this exact parent. Original loop order
gives ordinal1+seed*560+op*56+length_index*8+mode*2+sticky =683.
It is the first retained failure beyond accepted682. Prepare exact prefix1..683
with682 real predecessors, not a reset singleton or detached suffix. This adds
one genuinely uncovered original position, checks349696 bits/1366 guards and
683 flags/vstarts, but does not close full17920 or reproduce a new64-data-error
symptom. Existing682 preparation/model/checker can be reused only through a fresh
explicit successor; never change sealed inputs or rerun the accepted682 as a goal.
The full parent is an alternative source-ready preparation; its own budget is
unmeasured and cannot inherit4259s for682 calls.

## Next Action

Recommended new work: prepare exactly full e8/mf4 cap32 arithmetic from the pinned
original inputs above. If prioritizing a measured historical FP failure instead,
prepare original prefix683 with its full predecessor sequence. Continuouswhole1134
is the only existing full SoC ELF remaining here, but requires explicit serial
budget feasibility. None of these is authorized to simulate by this read-only
review. Do not repeat full777, MACC482, arithmetic accepted4/prefix5, FP50/682,
whole20 or Whole59; do not claim acceptance of original failed larger shapes by
running the small control instead.
