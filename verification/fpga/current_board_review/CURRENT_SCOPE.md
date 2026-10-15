# Current Historical-Failure Scope

## 2026-10-13 Evidence Reconciliation

### 2026-10-14 Remaining Runtime And Software Gates

Arithmetic acceptance remains18/22,86940 original calls. The new e16/m8
sentinel run reached its actual10800.076s timeout: return255, timed_out=true,
failure_seen=false and cancelled=false. The wrapper's later CANCELLED label
does not indicate an independent user cancellation. Service and collector
exited1; no full checker acceptance exists. See
[terminal failure](arithmetic_restart_original/m8_sentinel_mask_static_review_hilbert01/TERMINAL_FAILURE01.md).
The closed-trace diagnostic02 has now completed its sole admitted pass:
actual postprocessor wait0/348.596s, EOFtrue,2570844 rows/296607084 bytes,
80 pins and file stat unchanged. Hilbert's independent terminal status is
ACCEPTED_DIAGNOSTIC_ONLY, not DUT PASS:
[diagnostic terminal](arithmetic_restart_original/full_e16_m8_sentinel_vcs_m9_plan01/diagnostic02/TERMINAL.md),
[independent review](arithmetic_restart_original/m8_sentinel_mask_static_review_hilbert01/DIAGNOSTIC_TERMINAL02.md),
review JSON SHA256 `827814326368a77d17862be96c19fe0adad5bfd08e6a6dd22a1269c37bc0778d`.
3868 completed calls have full data/fresh/owner checks (1980416 results,
7736 guards,498972 output reads); source errors remain0. Call3869 is incomplete:
seed2/op18/VL0/mode1/vstart0, helper next index3, three pending uops and one
unmatched architecture suffix. Last retire/progress is cycle20211971;
maximum recorded progress gap3280 and completed-owner lifetime3306 do not
establish the final simulator cycle or rule out a post-trace stall. This
checked diagnostic prefix is not full4095 acceptance or Linux closure and
adds no shape/call to the accepted18/22,86940-call union.

The original diagnostic01 is preserved as an internal-budget failure:
actual wait1/598.981s,978944 consumed rows/111733676 bytes, not complete EOF.
Diagnostic02's new1800s admission was POSTPROCESS_ONLY, not a simulator
extension. Its successful348.596s full-file result cannot be attributed wholly
to sidecar code: work completed differs and machine load was not controlled.
The separate constructed unprofiled3.9 old/new median gain was1.36x; neither
that measurement nor a comparison of these two raw-processing runs isolates
all causes of the wall-time difference. No raw rescan follows this result.

The complete e8/m8 reference is independently accepted, but its DUT remains
runtime HOLD. Existing evidence does not support completion under10800s.
The parent has asked the user about e16/m8 full4095 up to3.5h and e8/m8
full4095 up to6h. Both requests remain unanswered, not DUT authorization;
no new DUT launch, retry or simulator timeout extension is permitted pending
that decision. A new/resumed goal does not clear these restrictions, and the
1800s postprocessing authorization does not grant either runtime budget.
See [reference acceptance](arithmetic_restart_original/e8_m8_sentinel_mask_reference_terminal_review01/REVIEW.md)
and [runtime analysis](arithmetic_restart_original/full_e8_m8_sentinel_vcs_m9_plan01/RUNTIME_RISK.md).

Fixed full10752 has passed independent original-C Host numerical checks and
compiled once per backend, but actual conditional positive-CFG costs are
3682553 SoC /3675660 Spike, above the current3M reference gate. This is a
software-cost HOLD, not a DUT result. Independent artifact review is pending;
no reference or DUT execution follows automatically. MACC full22400 separately
has an optimistic mandatory-store/read/helper floor3203200, already above3M:
[static feasibility](arithmetic_restart_original/macc_disjoint482/full22400_static_feasibility01/STATIC_PLAN.md).
Neither software-cost result changes accepted prefix777 or prefix482 into
full-parent acceptance. These limits are verification budgets, not ISA limits
or demonstrated RTL defects.

### 2026-10-15 Masked Unboxed e16/mf4 Full17920 Terminal Acceptance

The distinct original parent `rvv_fp_compare_unboxed_e16_mf4` (masked,
UNMASKED0/UNBOXED1/DK0) now has complete contiguous17920 source-port
acceptance on M9, not merely a reference or prefix. Actual simulator wait0/
7843.901512s, service success/exited0, collector wait0/7.834390s; no timeout,
failure veto, abort or retry. Full286720 result bits,35840 guards,17920
flags/vstarts,326144 helper instructions,8960 mode records,734720 fresh
stores,143360 input loads and10752 FPR committed writebacks are checked.
All89600 required memory and15360 nonempty target owners, including all-off
targets, complete:104960 alloc/done. The2560 VL0 targets remain separately
elidable; existing optional tokens still require complete pairing.

[Independent metadata terminal review](fp_compare_unboxed_masked_full17920_vcs_m9_plan01/TERMINAL_REVIEW.md),
JSON SHA256 `183255ca134542d7376b1427ad222aff76b145f5e8535277585bdc0a6add6430`;
collector SHA256 `f634b1a9f14ef079e90fa300a0b201f7c0941af0bbce8b439263628025b77921`.
Review rehashed16 small evidence/approval files; large CSV/strict identities
and input pin continuity inherit the sealed complete/collector chain, without
another CSV parse or large-trace hash. The event observer also exited0.

This accepts the full original masked parent source-port, not original Linux
execution or historical incident causality. FPR evidence is committed writeback,
not physical register readback. It does not close the separate alias-v8 parent,
other FP parents or any remaining arithmetic shape; arithmetic remains18/22,
86940 accepted calls. Old prepared01 HOLD is preserved. Not all objective gaps
are closed; remaining parent/Linux requirements below remain applicable.

### 2026-10-14 Unboxed e16/mf4 Full17920 Terminal Acceptance

Outside arithmetic22, the complete original unboxed/unmasked e16/mf4
source-port parent is independently accepted on M9:17920 contiguous calls,
286720 result bits,35840 guards,17920 flags/vstarts,326144 helper instructions
and10752 FPR committed writebacks (336 per seed). All89600 required memory
owners and15360 nonempty targets pair,104960 alloc/done;2560 VL=0 targets
are separately elidable. Actual simulator wait0/6687.051487s, systemd
success/exited0, collector wait0/9.037511s and observer wait0 are recorded.
The independent metadata review verified750 input pins and776 unique
input/evidence/approval pins:774 nonraw rehashed, two sealed raw identities
inherited without reparsing CSV/reference. Evidence:
[full17920 terminal review](fp_compare_unboxed_full17920_worker_review01/TERMINAL_REVIEW01.md),
result SHA256 `80158c54d11241ceca0cfcda1ae920244c29fa8e841cbe87e71299d38494999b`.

This supersedes the unboxed265/startup-only scope below, not its preserved
historical ERROR/unknown-exit record. FPR evidence is committed writeback,
not physical FPR readback or an accelerator operand snapshot. Original Linux
execution/incident closure remains open. The separate alias-v8 e16/m8 parent
still has only first700/17920 accepted; this result does not replace it or
alter the arithmetic22 count of18/22 and86940 calls.

### 2026-10-15 Unboxed FP32 e32/mf2 Full17920 Terminal Acceptance

The separate original failed parent
`rvv_fp_compare_unboxed_unmasked_e32_mf2` now has complete contiguous17920
source-port acceptance on frozen M9, outside arithmetic22. The strict worker
and actual stop-hook collector accepted286720 result bits,35840 guards,
17920 flags/vstarts and10752 FPR committed writebacks across3702091 CSV rows.
All89600 required memory and15360 nonempty target owner-bearing instructions
are checked for completion;2560 VL0 targets remain separately elidable.
Actual simulator wait0/8419.734125s, service success/exited0 and collector
wait0/7.933268s are recorded. Complete metadata states no abort, retries0
and843 plan pins unchanged. The event observer independently matched these
small receipts without rereading or hashing CSV/reference raw.

Evidence: [collector result](fp_compare_unboxed_e32_mf2_full17920_vcs_m9_plan01/prepared02/collector_result.json),
SHA256 `8e22456ac2001af5ef318341141147b6d8f5e70248f1ff3e898bdfc398e42de0`,
[terminal event receipt](fp_compare_unboxed_e32_mf2_full17920_vcs_m9_plan01/terminal_event_wait01/notification.json).
Hilbert's [independent metadata terminal review](fp_compare_unboxed_e32_mf2_full17920_entry_review_hilbert01/TERMINAL_REVIEW.md)
is ACCEPTED, JSON SHA256
`ec6fe13dd62e28abde015ed0b4951ff3095bcb237595de9c240485e3789ae396`:
16 small evidence/approval hashes freshly matched; full pin and large
strict/CSV identities are inherited from the sealed complete/collector,
not claimed as a new complete pin rescan or numerical reexecution.
This supersedes this parent's reference/startup-only status, not preserved
prepared01 entry refusals. It does not close the separate alias-v8 e16/m8
parent, any other FP parent, original Linux execution/history or incident
causality. FPR evidence is committed writeback, not physical readback.
Arithmetic acceptance remains18/22 shapes and86940 calls.

### 2026-10-14 Remaining Historical Arithmetic Work

Latest accepted union:18/22 shapes,86940 original calls;4 shapes/20160 calls
remain. Newly accepted e32/m4 completed its full5985 M9 run and independent
terminal metadata/identity review: actual simulator0/9010.678s, service
success/exited0 and collector wait0/16.913s;766080 results,11970 guards,
77805 helper instructions and389025 actual output reads. All1890 FP calls
retain483840 fresh input stores;29925 mandatory memory owners plus3762
nonempty targets pair completely, including117 op24 targets. The independent
review checked all5985 call records and65837 owner records, and rehashed1203
nonraw input/evidence/approval pins without a CSV/raw reparse. Evidence:
[e32/m4 terminal review](arithmetic_restart_original/full_e32_m4_terminal_review01/REVIEW.md),
result SHA256 `08032aedc12e65781f7455bb34c1715c68f50e70109f7ba28c4e70ac349245b6`.
This supersedes17/22 below. The union remains mixed-image source-port evidence,
not all22 on M9, a dedicated fflags oracle or original Linux/stall closure.

Previous accepted union:17/22 shapes,80955 original calls;5 shapes/26145 calls
remain. Newly accepted e64/m4 completed its full5985 M9 run and independent
terminal review: actual simulator0/8619.872s, service success/exited0 and
collector wait0/12.196s;383040 results,11970 guards,77805 helper instructions,
395010 actual output reads,241920 fresh FP stores and33687 required owner pairs.
Evidence: `arithmetic_restart_original/e64_m4_terminal_review01/result.json`
(SHA256 `43d55d6da766bf6a76d625fbc734780e975773d6363de49afb2b6a8c0ea769b6`).
The reviewer rehashed1134 nonraw pins and inherited the admitted closed trace
chain without reparsing it. This supersedes16/22 below; neither a dedicated
fflags oracle nor original Linux/historical-stall closure is claimed.

Latest accepted union:16/22 shapes,74970 original calls;6 shapes/32130 calls
remain. Newly accepted e64/m2 completed its full5985 M9 run and independent
terminal review: actual sim0/6231.264s, service0 and collector0;191520 results,
11970 guards,5985 returned-vstart checks,203490 output reads and33687 required
owner pairs. All1890 FP calls retain120960 fresh input stores. The reviewer
verified1048 current nonraw pins; sealed raw/log hashes were inherited, not
reread. Evidence: `arithmetic_restart_original/full_e64_m2_terminal_review_zeno01/REVIEW.json`
(SHA256 `937b861c0ef9f62a9abb54a2be7e7eac3688e746e4c101a1c81338c9e5f7aec4`).
This supersedes the15/22 milestone below, not the mixed-image union or original
Linux historical-stall closure boundary.

Latest accepted union:15/22 shapes,68985 original calls;7 shapes/38115 calls
remain. Newly accepted e32/m2 completed its full5985 M9 run and independent
terminal review: actual sim0/6749.046s, service0, collector0,383040 results,
11970 guards and197505 reads, including full FP/cache/mask and per-owner
validation. Evidence: `arithmetic_restart_original/full_e32_m2_terminal_review_zeno01/REVIEW.json`.
The parent additionally verified the47 small excluded log hashes; only the
two large raw logs inherit the sealed producer/collector hash chain without
reread. This supersedes the14/22 milestone below, not the mixed-image or
historical Linux scope boundary.

Latest accepted union:14/22 shapes,63000 original calls;8 shapes/44100 calls
remain. Newly accepted e32/m1 passed its complete5985-call M9 run and
independent terminal review: actual sim0/5461.652s, service0, collector0,
191520 results,11970 guards,101745 reads and33687 required owner pairs.
Evidence: `arithmetic_restart_original/full_e32_m1_terminal_review_zeno01/REVIEW.json`.
This supersedes the13/22 milestone below; the union remains mixed-image
evidence, not all22 on M9 or original Linux historical-stall closure.

Latest complete acceptance: e16/m4 has also passed independent terminal
review, bringing the union to13/22 shapes,57015 original calls;9 shapes/
50085 calls remain. Actual sim0/7082.897s, service0 and collector0 bind
4095 calls,1048320 typed16 results,8190 guards,266175 output reads and
23067 required owners. Evidence:
`arithmetic_restart_original/full_e16_m4_block_vcs_m9_plan01/terminal_review01/REPORT.json`.
This supersedes the12/22 milestone immediately below, not the original Linux
closure boundary.

Previous complete acceptance: e8/m2 and e16/m2 have both passed independent
terminal identity, actual exit and full-source-scope review. The accepted
arithmetic union is now12/22 shapes,52920 original calls;10 shapes/54180 calls
remain. This supersedes the10/22 milestone below, not the original Linux
closure boundary. Both new runs used the frozen M9 image.

- e8/m2: actual child0/4953.565s, service0, collector0;4095 calls,
  1048320 results,8190 guards,135135 output reads,23067 required owners.
  Evidence: `arithmetic_restart_original/e8_m2_terminal_review01/REVIEW.md`.
- e16/m2: actual child0/3914.347s, service0, collector0;4095 calls,
  524160 typed16 results,8190 guards,135135 output reads,23067 required
  owners. Evidence: `arithmetic_restart_original/full_e16_m2_block_vcs_m9_plan01/terminal_review01/result.json`.

Remaining full arithmetic shapes: e8/m8; e16/m8; e32/m8;
e64/m8. Neither partial m8 diagnosis counts as a completed shape.

Current admission map (milestones, not inferred live-process status):

| Remaining shape | Latest verified milestone | Still required |
| --- | --- | --- |
| e8/m8 | Old full run timed out;2601 calls checked diagnostically; sentinel reference accepted, new DUT on runtime HOLD | Complete original4095-call RTL acceptance; unanswered6h request is not authorization |
| e16/m8 | Sentinel DUT timed out; diagnostic02 reached complete CSV EOF and checked3868 calls, active3869 incomplete; independent diagnostic-only acceptance | Complete original4095-call RTL acceptance; unanswered3.5h request is not authorization; all old failures retained |
| e32/m8 | No full current-image acceptance in this union | Complete source-equivalent preparation and RTL acceptance |
| e64/m8 | Original scope statically verified; retained scalar-test instruction floor3085425 exceeds current3M gate | User budget decision, complete preparation and RTL acceptance |

The e64/m4 archive records a historical board PASS; its remaining task here is
current-image regression, not an established unfixed numeric bug. Likewise,
software preparation failures are not classified as RTL failures. Historical
Gather/Linux evidence gaps and the full FP-comparison parent remain separate
from this arithmetic table and are not removed from the overall objective.

Latest admission update: the unique full e32/m1 M9 worker has actually started
as `ara-arithmetic-original-e32-m1-full5985-m9-01.service`. Its retained
startup receipt binds the private ELF and frozen image, records CPU/trace
growth and the sealed exit hook. This is not terminal acceptance. No active
CSV reparse or long-run polling is authorized.

The full e64/m2 source/model proposal has independent static acceptance.
Only new software preparation, Host equivalence/negative checks and actual
compiler/helper/map/stack/cost review are admitted next. Its illustrative
cost may exceed the reference gate; neither Spike nor VCS is admitted yet.
All5985 calls,1890 per-call FP input refreshes and the complete272-byte
output remain mandatory. The accepted arithmetic union remains10/22.

The three historically stalled full arithmetic shapes are being checked with
their complete original source-derived call sequences, not accepted prefixes.
The independently admitted M9 e8/m4 and e8/m8 workers have started; launch
receipts are under `arithmetic_restart_original/full_e8_m4_dict_vcs_m9_plan01`
and `arithmetic_restart_original/full_e8_m8_block_vcs_m9_plan01`. Startup does
not establish terminal acceptance. Their fixed budgets and exit collectors
remain in force; no automatic retry or scope reduction is permitted.

The e8/m8 run has since reached its actual10800-second limit and was
terminated, return255, with no architectural acceptance. Its last visible
records are scalar mask-copy retirements, not proof of an accepted blocked
vector request or of continuous progress up to termination. The frozen trace
monitor's progress fflush requires COMMIT_WATCHDOG, which this run did not
enable; last file mtime therefore cannot distinguish exit flushing from late
progress. A bounded closed-prefix diagnostic is authorized to recover actual
completed-call and protocol state, not to substitute prefix PASS for full4095.
No budget increase or rerun has been authorized for this timeout.

The e16/m8 full4095 reference has completed once with actual reference and
audit exits0,2096640 result elements,8190 guards and528255 output reads.
Firmware cost2807400 is derived from its closed retirement ledger. See
`arithmetic_restart_original/full_e16_m8_block_unrolled01/READY.json`.
The corresponding M9 worker passed23 Host checks and independent entry review,
then started once as `ara-arithmetic-original-e16-m8-full4095-m9-01.service`.
Startup evidence confirms real CPU/trace growth and the frozen exit collector;
this is running evidence, not DUT acceptance.
Typed16 sentinel005b, physical8-register groups and the complete1028-byte
output including the four-byte tail remain checked.

The separate `HISTORICAL_SCOPE_RECONCILIATION_20261014.md` reconciles remaining
Gather11, Linux CSR waits, NF8 aggregate discrepancies and arithmetic22 scope.
Missing historical context is not a newly established current RTL bug. Source
ports do not substitute for original Linux execution or historical cause proof.

The original e8/m4 simulator has since exited0 in10573.339 seconds without
timeout or failure veto. Its postcheck failed because it required a backend
owner for an offset2 VSLIDEUP at VL1. A separately reviewed exact correction
has now passed one complete closed-trace audit in367.663 seconds:4095 calls,
2096640 result elements,8190 guards,4095 vstart readbacks,266175 output reads
and23067 required owners. The18 newly optional slideup targets had no actual
backend allocation; all117 nonempty op24 targets remained mandatory. See
`arithmetic_restart_original/full_e8_m4_owner_recovery_entry_review01/FINAL_REVIEW.md`.
The sealed worker remains NOT_PASS and its actual service exit1 is retained;
this is separate architectural recovery, not rewriting the failed service or
original Linux closure. No VCS rerun was performed.

The e8/mf2 closed-trace recovery has also completed and passed independent
terminal binding review:4095 calls,262080 result elements,8190 guards,36855
output reads and23067 required owners, actual offline audit0/134.161 seconds.
Its actual VCS exit0/1932.222 seconds is retained separately from the old
service exit1; the original erroneous worker NOT_PASS is not overwritten.
See `arithmetic_restart_original/e8_mf2_owner_recovery_entry_review01/TERMINAL_METADATA.md`.

Three further original complete scopes now have independent terminal binding
acceptance, without semantic CSV reparse: e16/mf2 (actual sim0/1677.074s,
131040 elements), e8/m1 (sim0/2909.582s,524160 elements), e16/m1
(sim0/2347.660s,262080 elements). Each retains4095 calls and8190 guards,
actual service exit0 and all23067 necessary owner completions. See
`arithmetic_restart_original/full_e16_mf2_terminal_identity_review01/REVIEW.json`,
`arithmetic_restart_original/e8_m1_packed_m9_entry_review01/TERMINAL_METADATA.md`
and `arithmetic_restart_original/full_e16_m1_terminal_identity_review01/REVIEW.json`.

The accepted complete arithmetic union is now10/22 shapes,44730 original calls;
12 complete shapes/62370 calls remain. This is a mixed M6/M7/M9 union, not
acceptance of all22 on M9 or original Linux closure. The earlier five-shape statement below
is retained as historical milestone, not the current count.
The next full e8/mf2 source-port has passed its single complete reference,
25 Host checks and exact independent M9 admission, and started once as
`ara-arithmetic-original-e8-mf2-full4095-m9-01.service`. Its subsequent separate
architectural recovery is accepted as recorded above. The accepted count is not increased
merely by reference PASS or simulator startup.

### 2026-10-14 FP700 Terminal Update

The current M9 continuous original first700 FP alias calls are independently
accepted at `fp_comparison_original/full700_terminal_recovery02/REPORT.md`:
358400 result bits,1400 guards,700 flags/vstarts and3396 required owners;
actual simulator exit0/4549.983 seconds,922 evidence pins unchanged. The retained
loaded service independently records normal exit0, not missing-unit defaults.
The old collector stopped on a removed-cgroup traversal race; that NOT_ACCEPTED
remains unchanged. Recovery hashes the closed trace and binds the producer's
full strict/generic check without rerunning simulation or semantic CSV parsing.
This covers the retained original call50 and681..700 contexts, not all17920
parent calls, historical root-cause proof or unmodified Linux execution.

### Full e8/mf4 Arithmetic Update

The complete original e8/mf4 cap32 source-port now has M9 producer and collector
acceptance at `arithmetic_restart_original/full_e8_mf4_o2_vcs_m9_successor02/prepared01`:
4095 calls,131040 results,8190 guards,4095 vstarts,4627616 rows. Actual simulator
exit0/7872.941 seconds; systemd exit hook records exited/0/success and the
metadata collector exits0. Required memory evidence includes20475 fixed helper
requests plus117 nonempty op24 targets, all observed with matching completion;
896 input pins remain unchanged. No semantic trace reparse or simulation retry.
This makes five complete shapes accepted across M6/M7/M9, not all22 or a
same-M9 acceptance of the earlier four. Separate final terminal short review
at `arithmetic_restart_original/full_e8_mf4_m9_terminal_review01/TERMINAL_REVIEW.md`
also accepts the binding. The three historical stalled full shapes remain distinct.

### Whole Continuous1134 Update

The complete original source sequence is now accepted on M9 at
`whole_register_original/continuous_packed_vcs_m9_plan01/prepared02`:
1134 calls and366 original exclusions,1233792 output-byte checks,2268 vstart
reads,145152 fresh input stores,154224 fresh output stores and154224 output
word reads. All4266 required owners completed, including864 nonempty targets;
270 empty targets may omit backend execution. Actual simulator exit0/7442.520
seconds; service hook exited/0/success and metadata collector exit0/15.752
seconds,746 input pins unchanged. This is one continuous execution, not a
union of the earlier20 partitions and59 fresh pairs. Separate terminal short
review at `whole_register_original/continuous_packed_static_review01/FINAL_TERMINAL_REVIEW.md`
also accepts the binding. It does not establish unmodified Linux execution or
turn366 excluded cases into tested cases; scalar harness packing is explicit.

This section supersedes older pending descriptions for the named scopes only.
The current M9 controls16 terminal has an independent receipt, pin and complete
CSV audit: 1010 pins, 16 actual child exits0, and all310350 event rows identical
to sealed M8. See `memory_candidate09_controls16/audit_resume01.json`.
M9 LOAD7 and STORE4 local acceptance does not yet establish the four SoC
alignment cases. The reviewed helper-owner successor was actually connected
and run: both M-mode simulators exited0 in about52s, but postchecking hit a
missing Spike-only `tohost` symbol in the SoC spec. The linked-failure guard
stopped the two Sv39 cases before dispatch. The old NOT_ACCEPTED is retained.
The backend-exit successor's once-only closed-CSV audit exited0: M-mode load697
and store698 checks, nine actual memory owners each,1253 pins unchanged.
Endpoint Host tests rejected62 negative cases and verified the unchanged oracle
step AST outside explicit endpoint handling. Fresh Sv39 load/store executions
subsequently exited0 in50.997/54.866s, each with checker0 and nine completed
memory owners. Independent combined terminal review accepts all four directed
architectural results:2790 checks,101070 rows,36 memory owners and56 CSR restore
readbacks. See `unmasked_strided_alignment_repair_zeno01/M9_ALIGNMENT4_TERMINAL_REVIEW03.json`
and `unmasked_strided_alignment_soc_m9_sv39_worker03/terminal_report01/REVIEW.md`.
The transient outer service's historical exit remains unknown; actual simulator
and checker numeric exits are durable. The original failed batch is not relabelled.
See `unmasked_strided_alignment_soc_m9_endpoint_successor02/closed_audit01` and
the original worker's FIRST_FAILURE_REVIEW.md.

Fresh source identity checking found all53 frozen `hardware/src/*.sv`/`.v`
members equal to the current verification worktree, with no missing member.
This establishes that subset's M9 identity, not a new539-file dependency audit.
Snapshot SHA256: `da19a3f298adc7453600db2cc931693a5329e2ad593569136bc0b797578cbe6e`.

The original small-exceptions20 inventory has been reconciled at
`masked_translation/exceptions_remaining20_review01/REPORT.md`: M6 accepts
e8/scenario0 and e64/scenario5; e16/scenarios0/2/3 have M2-derived coverage only.
The new M9 e64/scenarios1/2 now have independent terminal acceptance at
`masked_translation/unit_fof_e64_suffix_two_terminal_collector01/REVIEW.md`:
10962 checks,333756 rows,eight necessary memory owners,790 identity pins unchanged.
Actual systemd final exit is exited/0/success. No source-result suffix was waived.
The e64/scenario3 ordinary all-off load and e64/scenario0 true FOF shortening
now have a separate complete offline architectural recovery of their actual M9
traces:10958 comparisons,333389 rows,eight memory owners,936 pins unchanged.
FOF returnsVL4/start0; ordinary all-off retainsVL8/start0. The original failed
worker remains exited1/NOT_ACCEPTED; the separate recovery audit actually exits0.
See `masked_translation/unit_fof_e64_sc0_sc3_checker_recovery01/REVIEW.md`.
The remaining e8/e16/e32 fourteen cases subsequently passed on M9 with actual
child exits0, no abort/retry and real systemd exited/0/success. Independent
terminal audit accepts76726 comparisons,2288235 rows and56 memory owners;
1442 unique input/evidence pins match. See
`masked_translation/small_exceptions_remaining14_terminal_collector01/REVIEW.md`.
The same-M9 follow-up for e8/scenario0 and e64/scenario5 subsequently completed:
actual simulator exits0 in260.543/276.443 seconds,10958 comparisons,328069 rows,
eight required owners and830 unchanged pins. Producer and independent collector
record real exited/0/success hooks; see
`masked_translation/fof_two_singles_m9_terminal_collector01/EXIT_OBSERVATION.md`.
All20 now have source-single architectural acceptance on M9. This does not
establish original Linux signal/context or full-parent closure. The final separate
review at `masked_translation/fof_two_singles_m9_entry_review01/TERMINAL01.md`
also accepts the exact last-two terminal binding, without rerunning traces.

The completed M8 continuous prefixes fixed777, FP alias682 and MACC482 have
accepted full-data checker results and actual simulator exits0. A fresh joint
receipt/evidence audit checked1254 unique pins without drift; see
`audit_long_prefixes_resume01.json`. This audit preserves prior full-CSV semantic
checks rather than claiming a second semantic replay. Full original parent
matrices and Linux execution remain separate.

Segment full144 simulation exited0 after10179.499s with the capability endpoint
tohost77. The successor fixed only actual-ELF fatal-path resolution after the
old missing `replay_mismatch` error. Full offline audit exited0/291.113s and
independent review accepted120 numerical cases plus24 originally permitted
misalignment capability outcomes;983040 oracle bytes and288 checkpoints.
See `masked_translation/segment_full144_offline_recovery01/README.md`.
The original NOT_PASS is preserved. This is M8 source-derived capability
acceptance, not144 numerical PASS or original Linux acceptance.

## Post-M6 Candidate: Masked-Memory Exception Drain and Store Prefix

The current worktree now differs from frozen M6 in VLDU, VSTU and AddrGen.
M7 contains the first two changes; M8 adds the measured MMU-request repair.
A real four-module
VCS test reproduced a new VL9 masked-load first-element page-fault deadlock:
load completion disabled mask admission while MASKU still owed a third word.
VL8 was a completing control. The candidate retains the faulting owner and
drains its remaining predicates after prefix final grants, before load done.
Seven first-fault lengths1/4/5/8/9/12/16 pass the candidate load and store joint
tests. Load normal-cycle traces match M6 byte-for-byte; prefix final-grant,
nonzero-vstart, FOF and subsequent masked-load checks also pass locally.
The store candidate preserves an accepted AW prefix when a later indexed
address fails with WREADY held low: W is accepted at cycle41, B at52, done
at53, with correct data and strobes. Its normal masked-store cycle trace
matches M6 byte-for-byte. Shared-descriptor ordering was independently
reviewed; these local models do not prove actual lane-queue flush or SoC
exception recovery. Candidate07's independent build is accepted: 539 frozen
sources and 453 compile records match M6 except the approved VLDU/VSTU
changes and path relocation; simulator configuration is unchanged.
See [build handoff](memory_candidate07_build/BUILD_HANDOFF01.md).
Image SHA256 is
`e807e9243071ae078305ffa818f35c2902b33606fd20730fd6fe844a0924b7ba`.
The new VL9 real Sv39 load/store recovery tests both pass on M7; each has
914 independently expected on-device checks and a complete scalar retirement
trace. They cover first-element page fault, actual trap CSRs, leaf repair,
same-PC retry and subsequent masked load/add/store. Actual child exits are
0 without timeout/abort, taking177.290s and182.569s respectively. Results are
under `masked_translation/mask_drain_sv39_prepare01/vcs_m7_load01` and
`vcs_m7_store01`. These demonstrate recovery with the real lane queues;
internal flush signals were not captured, and original Linux ABI acceptance
and indexed-prefix recovery are separate scopes.
The unchanged M6 controls16 ELF set is now running on M7 in
`memory_candidate07_controls16/prepared01`, plan SHA256
`10320629ffe1ef6220d4480278b666f05f0dd1d4ca9f68a162a8d7e37b606bd5`.
Worker1917160 has published `PASS_M7_CONTROLS16_ARCHITECTURAL`:16 actual
successful child exits, unchanged inputs, no abort. All310350 CSV rows match
M6 in both noncycle fields and cycle values; changed rows and final-cycle
deltas are zero for every control. This includes representative RVV, QBS
and AKV controls, not all workloads.
The subsequent indexed-prefix recovery test timed out after900.107s. Its
target uop/CVX exception completed at cycle79705, but the first scalar load
in the trap handler did not retire. This is a separate failed SoC boundary,
now explained by a measured accelerator-MMU ownership deadlock. The bounded
same-image capture confirms the locally rejected address acquired ACC then
dropped its request without a translation response. AddrGen's request
qualification has been corrected; M8 same-ELF recovery has passed966 checks
with actual child/checker exit0, taking262.724s. All20 M8 recovery/control
tests are accepted; normal-path traces show no cycle changes in the stated
scope. See
[measured failure and probe plan](masked_translation/indexed_early_illegal_failure_review01.md).
M8 build/source/configuration checks are accepted, with only the approved
AddrGen change relative to M7. Image SHA256 is
`bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0`;
see [build handoff](memory_candidate08_build/BUILD_HANDOFF01.md).
M8's same-input validation has completed under
`memory_candidate08_recovery19/prepared01` (the final plan has20 cases,
despite the retained directory name).
The exact former failing indexed-store ELF is the single pilot; only after
its966 checks pass does the runner dispatch the19 remaining tests across
three workers: the two VL9 recovery ELFs,16 unchanged controls and one
accepted full50-round resident indexed-load control. The latter compares
against its M6 trace, while the16 controls compare against M7. The pilot is
accepted with its actual child/checker receipts and full162118-row trace;
the aggregate20-case result is `PASS_M8_RECOVERY3_CONTROLS16_RESIDENT1`,
with all actual child exits0, unchanged inputs and no abort. The16 normal
controls and full50-round resident indexed load compare1146852 complete rows
with zero cycle or noncycle differences.
See [repair and evidence](masked_translation/EXCEPTION_MASK_DRAIN_FIX.md).
Existing M6 runs do not exercise this candidate. The historical Linux e64/m4
VL8 stall is not closed by this distinct VL9 counterexample.

## Gather Counter Review: No Current Reproducer Established

The completed [request-to-done review](gather_liveness_review_current01.md)
rules out the proposed simultaneous credit increment/decrement in the current
configuration: VrgatherOpQueueBufDepth=2 blocks admission at count1, and
MaskuInsnQueueDepth=1 keeps a preceding data pop from crossing into a new
instruction's REQUESTING epoch. Source consumption precedes final result
completion. This is a static reachability finding, not a simulation PASS or
closure of the eleven archived stalls. No RTL change was made for this lead.
At that review, all twelve inspected implementation files matched frozen M6. A new counter
experiment requires a reachable request/pop sequence, not an injected pop
or a different queue-depth configuration.

## Next Original-Source Acceptance Runs

The disjoint VMACC e8/m4 complete first482 source preparation now passes Host
byte equivalence and its sole new Spike full-commit reference under
`arithmetic_restart_original/macc_disjoint482/full482_optimized_prepare01/work05`.
It retains481 predecessors, all five accumulator patterns,246784 results,
964 guards and6266 original helper instructions. Actual reference exit0
took2.124s with835145 firmware instructions; the raw audit checks fresh
per-call setup, original helper order and the full output oracle. Main
independently rehashed126 pinned preparation files and the reference receipt
link without drift. Ten error mutations are rejected, while corruption beyond
the original guard remains permitted. No DUT is yet launched for this482
sequence; old accepted single481/pair480-481 scopes remain separate. The
original22400-call matrix and Linux history remain open. Published scalar-only
time extrapolation is not a complete DUT estimate: formal admission must also
charge vector execution/wait cost and retain the fixed three-hour limit.

The source-faithful fixed-point e8/m4 first777 sequence has passed software
equivalence, the sole Spike reference and independent worker entry review.
It retains776 predecessors, all512 result bytes and both guards, original
24-instruction helpers and vxrm/vxsat/vstart operations. Scalar verification
cost is790055 firmware instructions, not an RTL speedup measurement.
The once-only full777 M8 simulation is launched under
`fixed_restart_original/full777_optimized_prepare01/vcs_m8_run01`, worker2093949
and simulator2093974, with plan SHA
`3334f5b20e069106f308a5540ea81edd5da36e0d6f2f87266988fed33442bb04`.
Main observed the live simulator in the whole-machine VCS roster; fixed
case/service budgets remain9000s/10800s with no automatic extension.
No full777 DUT acceptance is yet claimed. The original10752-call parent and
Linux execution remain distinct, and old single/pair acceptance is preserved.

The remaining38 negative-stride source campaign completed on frozen M6 under
`masked_translation/negative_stride_remaining38_batch01/sv39/vcs_m6_plan02/prepared01`.
Independent evidence audit `masked_translation/negative_stride_remaining38_batch01/terminal_resume01/TERMINAL.md`
accepts ten groups and38 unique source-derived cases,650641 checks. All actual
simulator and offline checker waits are0;1362 unique input/evidence pins match.
The62280086-row count comes from the existing full strict/generic checks; the
new audit verified CSV identities, not another full semantic traversal. Final
outer worker/service exit remains unknown. This is not an M8/M9 regression,
continuous original40-case history, original96-case parent or Linux ABI acceptance.

The original FP16/m8 alias first682 source sequence now has complete dynamic
Spike reference acceptance, not DUT acceptance, under
`fp_comparison_original/full682_vcs_m8_plan01/reference01/result.json`.
Actual reference exit0 took4.152s; strict raw-trace audit took96.304s,
checking682 calls/681 predecessors,349184 result bits,1364 guards,
682 flags/vstart outcomes and12592 original helper instructions. The
reference checks fresh source-vector payloads per call, not stale snapshots.
Main independently verified all138 reference input pins and the raw commit
hash without changes. The scalar optimization retains the original input,
helper and output contracts; detailed per-bit failure totals become per-byte
totals, while acceptance predicates are unchanged. Independent dynamic review
accepted156 pinned files with no drift; the worker/lifecycle Host tests pass.
The once-only M8 VCS run is now launched under `prepared01`:worker2079912,
simulator2080328, plan SHA
`ffdf6ce4cede184c6dc5ff817f7bb3ed92913ca91da28dddaaec54580e746f6c`.
Main observed the actual simulator live with CPU activity and an actively
written retirement trace; a read observed cycle42586/order29352 (the last
line was still being written, so it was not treated as a closed record).
No complete DUT acceptance is yet claimed. The original17920-call parent and
Linux execution remain open; this reference/launch is not evidence of an RTL fix.

Full original e64/m1 arithmetic has passed on frozen M7 with the single -O2
verification-software derivative:5985 calls,95760 results,11970 guards,5985
vstart checks and77805 original helper instructions, full order/unpartitioned.
Actual VCS exit0 took7544.534s; strict validation covers4794396 CSV rows.
Result is `arithmetic_restart_original/full_e64_m1_o2_vcs_m7_plan01/prepared01/complete.json`.
The four fully accepted cap16 arithmetic shapes (e8/mf8,e16/mf4,e32/mf2,e64/m1)
total20160 calls,322560 results and40320 guards. Other original shapes retain
their individual incomplete scopes; no original fflags oracle is invented.

The two missing Gather VI0 shapes have passed their genuine first112-call
prefixes on M7: e8/m4 in3963.540s and e16/m8 in3748.594s, actual exits0 and
unchanged inputs/no retries. Each preserves111 predecessors, checks57344
results/224 guards/112 vstarts/1456 helper instructions,128 physical predicate
bytes and2178 setup values per call. Evidence is
`gather_original_review/vi0_missing2_vcs_m7_plan02/prepared01/complete.json`.
This closes those numerical-prefix coverage gaps, not any original2688-call
child, unidentified stalled tuple, original Linux ABI or the11 historical stalls.

The e64/m2 zero-stride original16 DUT child exited0 in2831.976s without
timeout/software failure. Its sealed checker rejected the bootstrap at
retirement11 because the prior mstatus for CSRRS was uninitialized; the old
worker remains NOT_PASS/aborted. The source/image-bound reset-profile and
exact opaque ABI-save corrections have now passed an independent full audit
of the same closed CSV:16 cases,12 faults,16 ecalls,18188 checks,512 outputs,
32 guards and16384 memory words. Auditor actual exit0 took87.898s, no new DUT
execution. Evidence is
`masked_translation/zero_stride_e64_m2_original16_offline_recovery03/terminal.json`.
This is qualified offline architectural acceptance, not an RTL repair or
original Linux ABI/stall closure. The e64/m8 task also completed actual exit0
in3624.929s; its independently corrected closed-CSV audit exited0 in109.212s,
accepting16 cases,12 faults,16 ecalls,21260 checks,2048 outputs,32 guards and
16384 memory words. Its old producer NOT_PASS is preserved, no DUT was rerun.
Evidence is
`masked_translation/zero_stride_e64_m8_original16_offline_recovery01/terminal.json`.

Full original e16/mf4 arithmetic has passed on frozen M6:4095 calls,
65520 results,8190 guards,25 operations and3 seeds, with original order and
global RNG. Plan SHA
`17fc37e50f5420488a62872513fa77ce28ea89814ee2d5d3401ddcef27c751e0`,
independent entry SHA
`962d5bc3dd83c88ff34c9c54fc747d6d37d4572fa330c83d00384846fe072fe2`.
Actual VCS exit0 took6406.346s; the complete original order,65520 result
elements,8190 guards and4095 returned-vstart checks pass. A single independent
closed-CSV parse covers3987908 rows and3806630 retired instructions, with
45048 matched CVX requests/responses and23067 backend allocations/dones.
Independent auditor child exited0 in179.785s. Historical systemd service
exit was not independently retained and is not inferred from collected unit
properties; actual simulation and auditor receipts establish the stated
architectural acceptance.
The conditional terminal observer used pidfd on worker1842515,
observer1850493. Original attachment receipt is
`arithmetic_restart_original/full_e16_mf4_terminal_audit01/run01/attached.json`,
SHA `3f7369ecb73a8fab456556b6790ba96c0c5ddeb241d7ac03d1bcc2f7d51f90ff`.
Final acceptance is
`arithmetic_restart_original/full_e16_mf4_terminal_audit01/run01/TERMINAL.json`,
status `INDEPENDENT_FULL_E16_MF4_TERMINAL_ACCEPTED`. This does not accept the
other arithmetic shapes or the original Linux ABI.

Authentic negative-stride STORE `e16_m1_u1_s1_b3_m2_f0_g3` has passed on M6:
full64 results,2 guards and four complete8KiB memory checkpoints,
remap/refill, prefix poison and same-PC restart retained. Expected fault is
P-18/vstart5, not the historical erroneous P-2/vstart3. Plan SHA
`ea7add04987278b6c92bdcb720663ee5689021b26384f23111204b6938ed7a81`.
Independent input and worker reviews are under `masked_translation/store_entry_review01`.
Service `ara-negative-stride-store-m6-01.service`, worker1843736/simv1843794;
startup receipts record advancing CPU ticks2097->2394 and cycles14717->16989.
Checks target architecture-visible memory and same-owner completion; direct
delayed AXI B handshake or Linux signal-frame acceptance is not claimed.
STORE terminal service `ara-negative-stride-store-m6-terminal01` is attached,
MainPID1851244/child1851246, under `terminal_waiter01/ATTACH_RECEIPT.json`
and `ATTACH_STARTUP.json` in the STORE plan directory. Its initial observation
records `csv_started=false`; whole-run PASS and persisted actual return0
were required before the complete closed-trace checks started. The actual
simulator exited0/1111.624556s; no timeout, retry or abort occurred. Independent
terminal validation passed17275 checks in one complete CSV traversal, with
692 original inputs bound. It checked the expected cause15/P-18/vstart5,
2048-halfword refill, prefix visibility127, prefix poison36 and retried value166.
There are851880 rows,50 matching CVX request/response and architectural
requests,13 backend allocation/completion pairs and one expected exception.
Result SHA `8e56827652dc4af1290b16754882002c56fe934b9b23fb50d96fa22352fb8c25`
is under `terminal_waiter01/terminal01/result.json`; complete.json also binds
the actual audit wait receipt. Original Linux ABI and parent96 remain open.

FP alias first50 source/reference preparation is accepted with qualified
checkpoint evidence, but its first VCS worker was cancelled52.200s after an
independent review found a false required BOARD_CASE_BEGIN marker absent from
the actual ELF. Actual monitor return255/aborted=true/failure_seen=false is
preserved in `fp_comparison_original/fp_alias50_vcs_m6_plan01/prepared01`.
This is neither an RTL failure nor a PASS. The runner-only successor
`fp_comparison_original/fp_alias50_vcs_m6_realmarkers01` removes the false
BEGIN requirement while preserving the actual three PASS markers, simulator
completion, failure veto and full architectural oracle. Host and independent
changed-path review passed; the original source/ELF/image are unchanged.
New plan SHA `545cc6ae73198f80f334c1056fd7e76eccc22555c67ce84ea8f79599a5bc8560`;
worker review SHA
`d05a708998076cc5b616acdccf6e93927a887e34041e6eb8ff77df33aa79ddf7`.
The corrected worker completed with actual simulator exit0 in1977.806534s,
without abort/retry and with unchanged pins. It retains all49 predecessors
before original call50,25600 result-bit checks,100 guards and50 flags/vstart
checks. The independent terminal audit exited0 in141.799169s and accepted
one complete CSV traversal, with unchanged row delivery and input pins.
Its terminal receipt is
`fp_comparison_original/fp_alias50_terminal_eventcheck01/run01/TERMINAL.json`;
result SHA `ba165ca6084b4d77938656190733dddbeed8a7a13bb2750714a677fcd4a99f9a`.
This accepts the source-faithful first50 on M6: the historical call50 wrong
result did not recur. It does not prove that a particular existing repair
caused the difference. Full682/parent/Linux remains open; the cancelled
marker-checker attempt remains preserved.

## Full Original E32/MF2 Matrix Accepted On M6

The original unpartitioned e32/mf2 arithmetic restart program completed all
5985 calls,95760 element checks,11970 guards,5985 returned-vstart checks and
77805 helper instructions, preserving original order and three seeds.
Actual simulator exit0/10026.130593s, no timeout/failure/cancellation/retry;
producer complete SHA
`5ff4a9561be0460029a683be1f8864147bf0734acc7290882eb63cc9edb2e7e7`.
The attached independent terminal auditor traversed the closed CSV once,
actual child wait0/238.399099s, report SHA
`51eea3aa647d4d027dea8a6b1384bf85e2303607d483bce0089fa8101454be2c`.
6187577 rows contain5922689 retirements,65838 matching CVX/architectural
requests and33687 matching backend allocation/completion pairs, without
exception/replay. Pins are unchanged. Main observed both producer and audit
services still present, inactive/MainPID0/Result=success/ExecMainStatus0.
Evidence is under `arithmetic_restart_original/full_e32_mf2_vcs_m6_plan01`
and `full_e32_mf2_terminal_audit01/run01`. The old two-case CANCELLED record
is preserved. Acceptance is this full original shape, not all22 shapes or
Linux execution. Its original oracle has no explicit fflags assertion;
none is claimed here.

## MIN SoC Two-Source-Single Acceptance

Two original e32/m1 MIN source singles, call1292 (active all-qNaN) and
call1232 (all masked off), passed separately on the frozen M6 image.
The independently reviewed inputs retain the original 21 helper instructions,
144-byte output oracle, flags and vstart checks. Expected result bits are
0x7fc00000 and the unchanged seed 0x7fc12345, respectively.
Plan SHA `d695a5bdcbc72c1d411859fb4dc800899a71848adbd6fd7bf86927c77c875c5f`;
parent authorization SHA
`2ad535ba669ae50f8bfc3ad39bb3615faa604512fabcd52fbc1643d5ddaea992`.
Service `ara-nan-min-two-source-singles-m6-01.service`, worker1745502,
actual simv1745689/1745690 were observed running after 2m17s, each with
2m07s CPU time; trace files were 10051584/11116544 bytes. These are launch
and progress evidence only. Subsequent actual simulator exits were both0,
elapsed3081.964454s/2923.244139s, with no abort/retry and unchanged inputs.
Producer complete SHA
`c11e7965f77693e5215541410989a7972e9a60acf06bccc258b85d6dc039a7e6`.
Independent terminal child actual wait0/365.891143s checked each complete
CSV once; result SHA
`14705b5190ba343823b37c5c7652759b76679ea93ccd59316eacc0175c58a284`.
Both original144-byte output oracles and21 helpers pass, including exact
MIN opcode, flags0, vstart0, six-event protocol and unchanged row delivery.
Each trace has1852052 rows,15 CVX request/response pairs,15 architectural
requests and6 backend allocation/completion pairs, with no exception/replay.
Independent metadata review SHA
`36082e302b56c03ece0d1e22f0f195ac19a4a2fe3ee1d3e206208c0694b98576`
under `nan_min_soc_worker_review01/TERMINAL_METADATA_REVIEW01.md` confirms
802 equal pre/post pins and matching producer/independent summaries.
Host13 and dryrun passed; 766 consumed
pins bind the source references, checker and image. No RTL rebuild, retry,
or original-parent/Linux acceptance is implied. The full e32/mf2 arithmetic
matrix has its separate full-shape acceptance above; neither task replaces
the other. MIN acceptance is limited to these
two original source singles, not their full parent or Linux execution.

## Latest Repair: M6 Functional And Representative Regression Accepted

Two further authentic FOF source singles now have M6 architectural acceptance:
e8/scenario0 actual0/234.030818s and e64/scenario5 actual0/246.718597s,
no retry/abort,744 original pins retained. Independent closed-CSV checks pass
5477/5481 scalar equalities and full source/page/guard/CSR/protocol contracts.
E8 business-returned VL4/vstart0 is distinguished from the helper-restored VL8;
final out[5..8] remains explicitly unconstrained. E64 retains typed uint64
old-vd0x5b and VL8/vstart0. Neither case has an architectural CVX exception;
zero physical MMU requests are not claimed. Complete SHA
`aeada7563cde5c17c7df9ab8e28187b0df52882da0b282d061be810656bac5bb`,
independent result SHA
`0a305cbdd84a6acc88ab710356845ebef0e5b9a34fe8de3e4d39e3f1d72a2aa7`,
under `masked_translation/fof_two_singles_vcs_m6_plan01`.
Main actually observed both original/audit units still present with
Result=success/ExecMainStatus0 (command chunk e21a39); no collected-unit default
was used. Scope is two selected Sv39 sources, not Linux/all8 historical ELFs.

Reference preparation established executor acceptance for two source-faithful
max-reduction singles; subsequent independent SoC acceptance follows below:
original e32/m1 calls1294 (active qNaN, VL3/mask24) and1234 (all-off, VL3).
Their complete21-instruction helper and144-byte oracle check canonical
`7fc00000` versus exact seed payload `7fc12345`, flags0/vstart0 and CSR restore.
Each reference contains1857110 firmware retirements. The first call uses its
original Spike run with a separately reviewed offline CSR-delta checker;
the second is its first dispatch. Original STOPPED/observer error remains.
READY SHA is `11cc4d306bdc5a37976d13eca3ec164ab597b42406e47c294ba714ef8bcf7cfc`
under `nan_minmax_soc_prepare01/observer_recovery01/complete01`.
Independent terminal entry review accepts the reference evidence without
another raw parse. The two-job M6 VCS run now has complete producer PASS:
call1294 actual0/2761.372574s and call1234 actual0/2968.092482s, no abort/retry,
all input pins unchanged. Complete SHA
`7b54be692c8a6ad4c93326eaa4c5e46a3ebe4828dbdf8079cb94d1bd4b26add9`,
under `nan_minmax_soc_vcs_m6_plan01/prepared03` (not superseded prepared02).
Its independent closed-CSV audit now accepts both source singles. Actual child
wait returned0 in378.546319s; one traversal of each CSV checks the independent
bitwise oracle, all144 output bytes, original21 helper, CSR operands/state and
six-event protocol. Both input-pin sets remain unchanged. Result SHA
`80ce4b2c0de52d541f20ee87c364f54349e6e1446e9eab1f1d26db766b1cb5e9`,
under `nan_minmax_soc_terminal_audit01/run01`; original STOPPED/reference
checker-error records remain preserved.
Plan SHA `3b8e979de31f8b27b86f46014d7d3b6bf7cfc7ee59f4719b7d7fbac090c036ca`,
745 pins,5400s per simulation/7200s worker, no retries or extensions.
This is independent M6 SoC max-operation acceptance for the two exact source
singles. No min-operation or full-parent acceptance is inferred.

The authentic negative-stride masked-load single
`e16_m1_u1_s0_b3_m2_f0_g3` has one bounded Spike reference accepted by its
executor and an independent sealed-adapter static review. The actual reference
exited0 in15.256142s,836971 firmware retirements; checks retain64 destination
elements/two original guards/full8KiB memory, exact fault5 atP-18, original
baseP+22/stride-8, prefix poison and unchanged-PC vstart5 retry.
READY SHA `d20a279ff09bbad626141a386a12160634b0ad36ca82ff6da661c1c7ddcc4d52`
is in `masked_translation/negative_stride_load_original01`.
The single M6 VCS run now has independent terminal acceptance:
actual monitor0/996.679668s,17274 scalar checks,64 original results/two guards
plus64 separate extra-storage guards, four complete4096-halfword memory
checkpoints,2048-halfword refill, exact fault5 atP-18 and same-PC retry.
One complete827948-row CSV traversal preserves generic protocol checks;
its one CVX exception is the required load fault, not a rejected extra exception.
All690 original input pins remain bound. Complete SHA
`812fe100a941e5fa407a452f2ce9c2f5619343aa16004c38a916dbe75b00054a`;
independent result SHA
`74e71b439a3a9586c875ef078f1ff4c2e1f0852d8e35f00bf979396de9fd50ce`.
Both original and audit services were actually observed still present with
Result=success/ExecMainStatus0; the separate observation record preserves this
without relabelling the auditor's earlier not-queried field. Acceptance is one
source-derived Sv39 single, not Linux signalframe or the96-case parent.

Two complete small original arithmetic matrices now pass the reviewed
offline reference checker, using their original one-shot Spike logs:
e8/mf8 has4095 calls/65520 results/8190 guards/4406446 firmware instructions;
e32/mf2 has5985 calls/95760 results/11970 guards/5922051 firmware instructions.
All returned-vstart checks and complete source ordering are retained.
Reference status SHA is
`0edaf36f891f25675e9b8638f2d8a92eea3894e8f5916e345d5ee4ed36f465b3`.
The initial startup-console checker errors and interrupted offline attempt
remain preserved; no extra Spike invocation or raw replacement occurred.
The reviewed successor permits only the exact startup's complete aligned
zero BSS sweep, then requires byte-only runtime console writes. Original
oracle has no explicit fflags checks; this adds no fflags acceptance claim.
Actual offline child wait returned0 in153.626305s with no timeout, as
durably recorded in `recovery01/execution01/outcome.json`;229 input pins
remain unchanged. Independent entry review has accepted this reference
evidence. The M6 two-job batch has stopped on its first postcheck error.
e8/mf8's actual simulator returned0 after6279.050261s and its firmware reported
4095 calls/65520 elements/errors0, but the strict checker rejected
`Scalar store enables/value/register`. Its result is ERROR, not architectural
PASS. e32/mf2 was CANCELLED after6340.756759s when sticky abort stopped the
private process group; it is not a completed failure of the arithmetic oracle.
Both the batch and independent terminal watcher correctly remain NOT_PASS.
The first-cause diagnostic proved a missing checker GPR reset state at the
legitimate `c.sdsp s0,0(sp)` prologue. An independently reviewed successor binds
zero initial integer registers to the exact frozen M6 FF-regfile reset profile;
the complete original consume/finish oracle is unchanged. A single full e8
offline traversal now has actual auditor exit0/182.474729s,890 pins unchanged,
4095 calls/65520 results/8190 guards/4095 vstarts/53235 helper retirements and
all six-event protocol checks passing. Terminal SHA is
`e022019dcfee416efc0023ed8cb7e1b72797a13a34118aa99340ae65418c4710`, in
`arithmetic_restart_original/full_small2_e8_offline_recovery_audit01/run01`.
This is recovered full-e8 architectural acceptance, not a relabelled old
worker or a whole2 acceptance. Independent terminal metadata review now accepts
the result; see `arithmetic_restart_original/full_small2_e8_terminal_metadata_review01/REVIEW.md`,
SHA `69370e2ed641355f7abcaea048f5054abc00658e356c3808e1c148b09ca13909`.
The original e32 cancellation remains; the independently reviewed standalone
full-e32 successor is now started under
`ara-arithmetic-full-e32-mf2-m6-01.service`, worker1691221/simv1691277.
It retains5985 calls/95760 results/11970 guards/77805 helper retirements,
unchanged source/model/ELF and exact M6 reset profile. Jobs1, simulation10800s,
worker12000s/service13200s; no automatic retry/extension. Plan SHA
`b75d801b6533b73bfa9127ff695b60642a421535f9528202b07248fc3f368c93`,
entry SHA `2618f028a6e488a31a14736193b0684d985eef46a55873e18bceef1631cf8134`,
parent SHA `103456cd1b5e2a66506a784ff9fb0b057511f135c54fcd26764be58bc86d2ffd`.
This is executing, not terminal acceptance. Full22-matrix acceptance remains
absent.

Recovery168's returned Gather numerical tuple has now been
[deduplicated against accepted83 and measured prefixes](gather_original_review/gather_recovery168_tuple_dedup01.md):
e8/m4/op3 VI31,seed0/scalar0/VL256/mask0/vstart128 has no exact match.
The original first66-call preparation now has source-preparer Host/Spike
acceptance, preserving65 predecessors,33792 full-capacity result reads and132
guards. Its actual firmware trace reaches HTIF after1353294 instructions;
all13 helper instructions appear66 times. READY SHA is
`f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649`.
Independent reference audit initially held because Xuantie14.1 did not
rebuild the original Linux ELF. That first non-equivalence remains recorded.
A fresh Buildroot14.3 reconstruction now matches the entire archived ELF:
both SHA256 `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
The actual single compile exited0; supplemental proof SHA is
`7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd`.
Successor READY02 SHA is
`11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc`;
old READY, SoC ELF and reference raw remain unchanged. Independent reference
audit now accepts the66-call numerical prefix: audit SHA
`3a9c52768d5244fdc803779ee58744fa243e6946bdddfd953b574d62b0942a4d`,
actual offline child rc0/no timeout in35.552925s. It checks one complete raw,
33792 results/132 guards,13 helper instructions66 times, actual capacity512
and vlenb128, with input pins unchanged. This established reference acceptance;
the subsequent M6 architectural-data recovery is described below.
A one-case M6 VCS successor has finished with actual monitor returncode0,
no timeout and both firmware PASS gates. The frozen generic trace validator
reports VALID with1317045 rows and zero CVX exceptions. The original strict
checker rejected the legitimate `arch_start` event at CSV line14; its worker
ERROR/NOT_PASS is preserved. A separately reviewed offline recovery will
validate all six trace event types through the frozen protocol checks and
retain the complete66-call numerical oracle. No new DUT run or RTL change is
justified by this checker error. The reviewed recover02 offline traversal now
has architectural-data acceptance: actual process exit0,94.335351 seconds,
one unchanged CSV traversal with33792 results/132 guards/66 vstarts/858 helper
retirements,730 paired CVX requests/responses and352 paired backend micro-ops.
All input pins match before/after. Recovery result SHA is
`c86bf85d2b4f6215675b8cccd41f3545b1f2ad79b0873c0470a13dc2f81b6d6e`;
actual exit evidence is in
`gather_original_review/e8_m4_ops3_prefix66_event_recovery01/offline01/actual_exit.json`.
The independent [terminal review](gather_original_review/event_recovery_review01/TERMINAL_REVIEW03.md)
accepts this recovery without a second raw traversal; it checks the reviewed
parser's result and actual exit evidence, not an independent rerun of the CSV.
The original worker ERROR/NOT_PASS/INTERRUPTED and the first recovery-admission
rejection are not relabelled. This accepts the66-call numerical prefix only.
Source/configuration maps this
returned tuple to call66, but the
snapshot lacks measured current vlenb/VL/vstart and does not identify the later
stalled call. Original physical predicate storage is128 bytes, all cleared
each call; m4's logical mask extent64 bytes does not justify shrinking storage.
The11 historical unknown Gather stalls remain open.

Four further archived NF2 failed-single geometries have
[independent M6 terminal acceptance](masked_translation/segment_review/nf2_remaining4_terminal_audit01/terminal01/REVIEW.md):
u0/s0/b1/m2/f1, u1/s1/b3/m2/f0, u0/s1/b5/m3/f1, u1/s0/b1/m3/f0.
Actual child rc0 is durably recorded;1759.444633 seconds, no retry/abort.
One complete CSV parse checks1308379 rows/1307708 retirements,3567 scalar
checks and eight full checkpoints, with721 pins unchanged. Faults restart
at2/5; all-off cases have zero page faults and checked precleanup memory.
Both64-element fields, guards,8KiB memory, page tables and CSR checks pass.
Result SHA is `79037611e05a12289eb6734b836f8cbcb5c28658bd0a88f3002fc895d5bb51ee`.
This pilot extends exact source-single coverage, not full96/Linux acceptance.
The remaining34 software references have independent reference acceptance:
28913 checks,68 checkpoints,483 unchanged pins; this is not DUT acceptance.
The remaining34 and unchanged J4 ELF now have
[independent M6 terminal acceptance](masked_translation/segment_review/nf2_remaining34_terminal_audit01/terminal01/REVIEW.md).
One traversal of each of ten CSVs checks12081073 rows,33046 scalar checks,
76 checkpoints,16 page faults and38 ecalls, with1379 pins unchanged.
The actual audit child wait returned0. Result SHA is
`b9fb37c4fa561fedb9df805bcf242d77d0c5711469e04a3d5384d17dc63ea6f0`.
Together with the pilot4, this establishes40 distinct failed-source geometries
on M6; J4's two positive controls remain separate. Full96 parent/Linux
remains open. Following this acceptance, NF7's24 unchanged ELFs/original96
trials have now all returned PASS/int0 under `ara-nf7-current96-m6-02.service`.
Producer complete status is `PASS_M6_NF7_SOURCE_DERIVED96_GROUPS24_NOT_LINUX`,
aborted=false/retries0/pins_unchanged=true. Independent event-driven terminal
audit now accepts all24 CSVs/original96 trials:24531873 rows,284816 scalar
checks,168 checkpoints,72 page faults and96 ecalls. All1973 pins were checked
before/after; actual auditor wait returned0 in2298.091310s, no retry.
Result SHA `afc630374ff028f7dde1c570c278000423efafe7a75ba0a7a5a266a1057ac784`,
REVIEW SHA `96798ef769e443164bec5b90b369a353585d313c13c7800debd5dfa37c63ec5c`,
in `masked_translation/indexed_review/sv39/nf7_m6_terminal_audit02/terminal01`.
This is complete source-derived96 M6 acceptance, not original Linux execution
or proof of its unidentified historical failure phase.

The original unboxed/unmasked FP16 mf4 comparison's first265 natural calls
now have [independent architectural-data acceptance](fp_compare_unboxed_prefix265_terminal_audit01/recovery01/REVIEW.md)
on M6. One CSV parse checked741981 rows/730922 retirements,4240 result bits,
530 guards,265 fflags/vstart reads and4587 original helper instructions;
761 pins remain unchanged. The historical first-failure call265 now returns
flags0/vstart0 and correct data. No new RTL change was needed.
The original batch remains ERROR: its legacy command checker confused the
historical Linux name with the port's TESTCASE name and discarded the child
exit metadata. The recovered conclusion is explicitly
ARCHITECTURAL_RESULT_ACCEPTED_PROCESS_METADATA_ERROR; child/service numeric
exit remains UNKNOWN. Full17920 parent and Linux execution remain open.

The current min/max NaN evidence gap is now measured by the
[active-NaN module matrix](nan_minmax_active_matrix01/REPORT.md):84 points,
min/max at FP16/32/64,1/4 lanes, VL35/vstart0. All-qNaN active sources return
canonical qNaN with flags0; participating sNaN sets NV16; all-off qNaN/sNaN
preserves exact seed payload and flags0. Real operand queues/VMFPU/FPnew and
cycle probes passed with current hardware hashes unchanged. No new RTL repair
was required. Predicate and SLDU-tree supply are modeled; this is module
acceptance rather than original Linux/whole-SoC source replay.

The original integer merge e16/m8 natural98 prefix has now passed
[independent full-oracle terminal acceptance](merge_original_prefix98_terminal_audit01/terminal01/result.json)
on frozen M6:98 original calls with97 predecessors,50176 result elements,
196 guard elements and98 returned-vstart reads. One complete CSV parse checked
2019442 records/2015140 retirements and746 before/after pins. Actual case rc0,
3145.854479 seconds, no abort/retry. Result SHA is
`ec838311b3c153252878fae6b96173b20a9164048b2d3701f602d4ef93d30e31`.
This covers the exact source-derived98 prefix. The historical stopped tuple
is unknown; full2688 child and original Linux replay remain open.

The RVV-01 indexed-overlap observation is no longer an unlocalized hypothesis:
M5's unchanged reference03 fault-ov1 program produced the bad address, and its
bounded wave plus independent static review identify cancelled mixed-index EEW
normalization. See [Repair06](indexed_overlap_original/REPAIR06_ROOT_CAUSE.md).
The minimal dispatcher dedup repair has an accepted independent M6 build. Its
full50 fault-ov1 DUT run has returned PASS/exit0 in 3059.083465s, with 21595
checks and 1600 faults/repairs/retries. Independent full-CSV acceptance has passed
([pilot review](indexed_overlap_original/repair06_pilot_audit01/REVIEW.md));
The resident-ov1 control has also passed independent full-CSV acceptance:
50 rounds plus the original masked restart, 1632 outputs, 102 guards and
5215 checks; see [resident review](indexed_overlap_original/repair06_controls_audit01/RESIDENT_REVIEW.md).
The fault-ov0 control has subsequently passed, and all three cases now have
[independent whole3 acceptance](indexed_overlap_original/repair06_whole3_audit01/REPORT.md),
including recorded actual worker exit0. Combined evidence retains 48405 checks,
4832 outputs and 302 guards. The bounded wave has separately
confirmed conversion/capture/replay order and corrected MMU/CSR address.
The separate48 regression has finished and passed
[independent terminal review](gather_repair05/m6_regression48_terminal_audit01/REPORT.md):
exact48 DUT programs accepted, all16 normal control full CSVs byte-identical
including cycles (310350 complete event rows), with755 plan and372 evidence
pins unchanged.
It started only after the strict predecessor
gate ([launch audit](indexed_overlap_original/repair06_followup/fresh02_launch_audit01/REPORT.md)).
There is **no observed cycle regression in these16 normal controls**; this does
not establish performance for every workload, especially unmeasured indexed or
mixed-layout conditions.
Older rows below retain their original
image-specific evidence and must not be reinterpreted as current M6 results.

The M5 Gather repair has separately accepted both original98-call prefixes and
the representative48 regression; see [current repair index](CURRENT_REPAIRS.md).
Neither establishes closure of the eleven unidentified historical stall trials.
The M6 e16/m8/op1 original98-call prefix has now independently passed its full
50176-output/196-guard source oracle
([case acceptance](gather_original_review/e16_m8_ops1_prefix98_terminal_audit01/REVIEW.md)).
The capacity1024 e8/m8/op1 prefix66 has also passed its reviewed, bounded single
M6 VCS run and [independent terminal audit](gather_original_review/e8_m8_ops1_prefix66_terminal_audit01/REPORT.md).
It retains all65 predecessors and the full67584-output/132-guard oracle;
actual simulator rc0 and 4052.291789s are recorded. Neither prefix is
full2688-call or exact historical-stall closure.
The e16/m8/ei16 original98-call prefix has now passed its bounded M6 VCS run
and [independent terminal audit](gather_original_review/e16_m8_ops20_prefix98_terminal_audit01/REPORT.md).
It retains all97 predecessors, dynamic/OOR indices and the complete
50176-result/196-guard oracle, including call66 OOR terminal0 and call98 data
terminal538 with all85 active OOR results0. Actual numeric simulator rc0 and
3365.877068s are recorded; the original disk-plan SHA and786 input pins were
verified, not only an in-memory plan. This is not full2688/Linux closure.
The e16/m8/vi31 natural98 prefix has now passed
[independent terminal acceptance](gather_original_review/e16_m8_ops3_prefix98_terminal_audit01/REPORT.md)
on the unchanged M6 image:855 input pins,11 evidence pins,98 original13-instruction
calls,50176 results and196 guards. Unsigned immediate31 and original scalar0
are retained; even VL1 reads source31=32689, not VX0=61881 or an invalid zero.
The e8/m8/vi31 natural66 prefix has now passed
[independent terminal acceptance](gather_original_review/e8_m8_ops3_prefix66_terminal_audit01/REPORT.md):
actual case rc0, 3559.067485s, 66 original calls/65 predecessors, all67584 byte
results and132 guards, with931 input pins and11 evidence pins unchanged.
VL1 correctly reads source31=177; fullcap output checks do not imply target
VL1023/1024 execution. This remains a bounded SoC source port, not full2688 or
original Linux ELF acceptance; the outer service exit is unknown after GC.

The original e8/m8/vi0 first112 reference successor has passed
[independent reference acceptance](gather_original_review/e8_m8_ops2_prefix112_audit02/REVIEW.md).
All112 original calls,114688 result bytes,224 guards and112 returned-vstart
checks match. The first independent audit incorrectly rejected the original
no-side-effect post-HTIF parking loop; that failed attempt is retained. Audit02
checks the exact original parking PC/encoding, rejects13 unsafe variants, and
counts2263 park records separately from5002732 firmware commits through HTIF.
It does not relax the numerical oracle or the5050000 reference-step ceiling.
The DUT runner passed55 Host checks and
[independent frozen-plan review](gather_original_review/e8_m8_ops2_prefix112_vcs_m6_runner_audit01/REVIEW.md).
The single authorized first112 M6 VCS run has completed: numeric case rc0,
8372.603878s, no abort/retry, unchanged pins, original COMPLETE/PASS:1.
The original114688-result/224-guard oracle passed. Plan SHA remains
`bb3b5302ce2c65ec91874c22ed85705488aae4ba2043ad32b285ba60c6d81c11`;
1098 pins, case9000s/service10200s, no retry/build/FSDB.
Later static review identified a potential unused-helper interior-PC checking
gap, not an observed DUT error. The frozen worker remained unchanged. The
[independent terminal supplement](gather_original_review/extra_helper_terminal_gate01/terminal01/REVIEW.md)
now accepts this actual run: single-pass4887389 CSV records, every retirement
PC/encoding matched the ELF, all13 selected PCs112 times, capacity once,
vector/CSR total1236, all19 unused helper ranges zero, no extra RVV, both raw
logs free of failure markers. This supplements rather than replaces the full
data oracle; it does not claim the old checker generally repaired. Outer unit
exit is unknown after collection, not assumed0. Only this112-call prefix is
accepted, not full2688 or original Linux execution.

The original e16/mf4 sparse ordered-reduction single has passed
[independent DUT terminal acceptance](ordered_reduction/original_e16_mf4_terminal_audit01/REVIEW.md):
numeric case rc0,3470.200884s, all144 output/guard bytes, NV16/vstart0,
one original21-instruction helper, no unused helper retirement,738 current pins
and733 old-plan pins unchanged. Its first plan was never launched after the
Host counterexample; successor plan02 repaired the checking gap without
reducing the data oracle. Restore instruction retirements and saved-zero source
operands are verified, but post-restore CSR state was not directly read back.
That earlier acceptance covers only the reduced single. The subsequent full
e16/mf4 parent acceptance below supersedes its call-coverage limit, not its
Linux execution boundary.

The remaining nine original shapes have completed their once-only three-way
M6 VCS batch: all nine actual case returncodes0, no abort/retry and unchanged
pins. Each took3004..3424 seconds. Their
[independent terminal result](ordered_reduction/original_remaining9_terminal_audit01/terminal01/result.json)
accepts all nine reduced singles after nine complete CSV parses,1296 oracle
bytes,60480 fixture-field reads and1438 before/after file pins. The original
21-instruction helpers, unused-helper ranges, actual PC/encodings, NV16 and
vstart0 are checked. Restore writes and saved operands are observed, but
post-restore CSR state is not directly read back. Complete SHA is
`d2b57da8b703fb5e301e3c584856be1d802bb5b0c688c72accef715e531330bc`;
independent result SHA is
`1c42f3ab98f80a6f90e53cafb121dea65ddfdc28afcda8ca96aa07b7817b1367`.
Together with the separately accepted e16/mf4 and e32/m1 singles, the11
inventoried shapes have measured single-scope acceptance. See the
[resume ledger](RESUME_20261011.md) for that historical milestone.

The e16/mf4 full6720 original parent now has complete M9 source-port
[independent terminal acceptance](ordered_reduction/full6720_e16_mf4_vcs_m9_plan01/TERMINAL_REVIEW.md):
decision `ACCEPTED_M9_FULL6720_SOURCE_PORT_NOT_LINUX`, review JSON SHA
`78427b0101fd2f57b78993ddbf0374c80dcb3588ae6240991645d0e0e9e296b3`;
actual simulator0/3076.519100s, actual service success/exited0 and collector
wait0/4.476907s, no timeout/retry. Original contiguous8x7x4x5x3x2 history,
967680 output/guard bytes,6720 flags/vstarts and141120 helper instructions
are accepted;33600 memory plus5760 target owners complete,960 VL0 targets
may elide. Collector pins unchanged; the terminal event observer checked
metadata only, not another CSV parse. This closes one full reduction parent
source-port scope, not the other ten full6720 parents or original Linux
execution. Those ten retain selected-single acceptance only.
These latest updates qualify the older remaining-work statements below; they
do not close the historical Linux fault schedule, other entire parent matrices or
unmatched records.

Initially a read-only evidence audit after candidate02 NF2 completion; updated
with the subsequently measured candidate03 focused11 and representative16 runs.
The representative replay reused the image with no build or production edit.
This is a family-level remaining-work ledger,
not original-record closure: **871 failed, 198 stalled, 47 mixed and 124
unexecuted ELF records are not independent bugs**. Original and partition
records overlap. No statement below closes all871 or all198.

Authority: [ALL_FAILURE_REVIEW.md](/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/ALL_FAILURE_REVIEW.md)
and [STALL_TRIAGE.md](/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/STALL_TRIAGE.md),
plus current [README.md](README.md) and terminal artifacts below. The earlier
[remaining_scope.md](remaining_scope.md) is a historical static inventory;
its pre-repair pending statements do not supersede later measured evidence.

## Version And Acceptance Boundary

| Evidence version | What is established | What is not established |
| --- | --- | --- |
| **M3**, `/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign` | Scalar-insertion focused11 PASS (M); exact M2 ten smokes and six singles **16/16 PASS**, all16 full cycle-bearing CSVs byte-identical to M2 (N) | No full38 rerun or new memory-family acceptance on M3; M2 NF7/alias jobs are not M3 results |
| **M2**, `/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign` | Build, three real-Sv39 ELFs and ten ordinary/QBS/AKV smokes PASS; extended8 successor02 PASS; NF2 four-case ELF PASS; arithmetic38 **38/38 PASS** (K) | Full historical memory family or Linux ABI; selected38 are not the original22-shape arithmetic matrix |
| **F4**, `/home/wangwy/fpga_runs/current_board_integration_final04/campaign` | 45/48 initial ELFs PASS; the three extension matrices subsequently PASS in retained same-image successor01 | Initial campaign remains FAIL (one TIMEOUT, two CANCELLED), not rewritten 48/48; F4 lacks M2's three later memory changes |
| NF7 and mask-logic alias complete on **M2** | NF7 actual24 groups/original96 trials independently accepted,284816 comparisons and168 checkpoints; see `masked_translation/indexed_review/sv39/terminal_audit01/REPORT.md`. Alias tuple3 and retained prefix3 have terminal PASS,262 distinct original trials | No whole-family, M4 or Linux closure; retain exact frozen M2 identity |
| **M4**, comparison-source candidate | Authentic19 source singles and16 representative controls independently audited PASS; first e8/m2 also passes measured origin0/bit84 writeback gate. Three additional FP source controls PASS, two measured M3 failures repaired, zero-start complete cycle CSV unchanged. Evidence in [SOURCE_ORIGIN.md](comparison_alias_original/SOURCE_ORIGIN.md) |15 of16 representative cycle CSVs match M3; restart_compare final cycle30318->30319, all noncycle fields unchanged. No full4032-case parent or historical Linux acceptance |

F4 snapshot SHA256: `0f16be2b3215e44aee4be5450d391e00e05a37a8e573c1fc4af3fbe2c9472671`.
M2 snapshot SHA256: `b185f9fd8cc4a75ce5ab5ef240fb621511affd673bbc8b43fb7a2e8d64bad8a9`.
Their ledgers differ only in `addrgen.sv`, `vldu.sv`, `ara_sequencer.sv`, and
the relocated filelist/Bender metadata. M2 inherits the earlier arithmetic,
slide, comparison and extension fixes; K now supplies actual same-program
candidate02 replay evidence for the38 selected non-smoke programs.

M3 snapshot SHA256: `382af2912634002ceecbaa44b8e8f0fb8262ab6aeb30e52d66a9bb0268508a2f`.
Versus M2, only production `ara_dispatcher.sv` differs: internal vstart=0 in
VMVSX/VFMVSF, retaining the architectural CSR empty-operation gate. Relocated
filelist/Bender metadata also differ. The accepted focused repair scope does
not relabel all M2 tests as M3 PASS; N supplies actual representative replay.

## Exact Program Evidence Key

Paths below are relative to this directory unless prefixed M2/F4. Acceptance
uses recorded terminal results with separate frozen-image identities.

| Key | Exact accepted programs / evidence |
| --- | --- |
| A | F4 `singles/summary.json`: `maskslide`, `restart_compare`, `reduction_fflags`, `m8widen`, `wholemove`, `slide1up_prestart`; `combined/summary.json`: `all`. [integration/README.md](integration/README.md) maps originals and selected tuples. `slide1up_prestart` is directed, not historical original. |
| B | F4 `extended/summary.json`: `slide_source_e32`, `slide_source_e64`, `m8widen_nonzero`, `wholemove_layout`, `extended`; these are explicit supplements, not original Linux programs. |
| C | F4 `gather/summary.json`: `gather_original` (genuine `rvv_permute_restart_e16_m1_ops0` vv source), `gather_prestart` (generic vx, historically **board_tested=false**). |
| D | F4 `comparison/summary.json`: `active_snan`, `no_snan`, `all_off`, `tail_vl15`, `prestart_snan`; `comparison-matrix/summary.json`: `prefix_quiet_tail`, `matrix_e16`, `matrix_e32`, `matrix_e64`. [comparison/README.md](comparison/README.md) explicitly distinguishes archived assembly/current reconstructed oracle, original selected all-off input and derivatives. Not full original comparison-program replay. |
| E | F4 `large-offset/summary.json`: `e8_m8_single`, `e8_m4_single`, `e8_m4_sequence`, `e8_m8_sequence`, `e16_m8_single`, `e16_m8_sequence`; six original-source full-oracle ports, 15 target calls. |
| F | F4 `extension-original/summary.json`: `extension_overlap_vl127`; `extension-matrix/summary.json`: e16/e32/e64 m2 vf2 matrices. [extension_overlap/final04_successor01/status.json](extension_overlap/final04_successor01/status.json): `extension_e32_m4_vf4`, `extension_e64_m4_vf4`, `extension_e64_m8_vf8` all PASS. Original VL127 plus six 24-trial derived matrices, not all42 archived ELFs. |
| G | F4 `flags-sequence/summary.json`: `flags_sequence`; `reduction-epoch/summary.json`: `all`. Directed continuous-instruction supplements, distinct from the original reduction selected point in A. |
| H | M2 `sv39/summary.json`: `alloff_fault`, `active_fault_retry`, `alloff_valid`; each709 checks. Ten M2 smokes PASS with input ELFs and complete cycle-bearing CSVs byte-identical to F4, per [COMBINED02_ACCEPTANCE.md](masked_translation/COMBINED02_ACCEPTANCE.md). |
| I | [extended8 successor02 complete](masked_translation/sv39_extended/candidate02_extended8_02/complete.json): `unit_load_retry`, `unit_store_retry`, `positive_load_retry`, `negative_store_retry`, `zero_load_retry`, `zero_store_alloff`, `fof_shorten`, `fof_masked_suffix`; 6227 checks, lastcycle1055787. Earlier01 remains CANCELLED after5072 checks, not PASS or a demonstrated RTL failure. |
| J | [NF2 DUT_REPORT.md](masked_translation/segment_review/sv39/DUT_REPORT.md): b3/split1/mask24 load/store genuine failed-single sources, b5 counterparts historical positive controls; four PASS,4133 checks,lastcycle1446260. Real Sv39, unchanged-PC vstart5 retries; not original Linux ELF execution. |
| K | [arithmetic38 complete.json](integration/memory_regression_plan02/complete.json): **PASS_38_CANDIDATE02**; [run.json](integration/memory_regression_plan02/replay/run.json) COMPLETE, PASS=38, completed2026-10-10 23:41:48 -07:00. Replays the38 non-smoke F4 programs above with pinned input ELFs/oracles. Plan SHA256 `1410586ddc6e00f7c55239f807497d214c1802c5727dbfb1e0ec1d684841a3bd`; recorded image identity `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`. This name does **not** mean the old RVV-02 22-shape arithmetic matrix was replayed. |
| L | NF7 `masked_translation/indexed_review/sv39/`: reference01 group00; reference02 groups01/06/18/23; reference03 remaining19 groups. All24 status records read; trial membership exactly0..95. [indexed review](masked_translation/indexed_review/README.md) preserves original indexed NF7 identity and original-C equivalence limitation. Reference progress prose predates aggregate completion; status files and exact membership take precedence. |
| M | [M3 focused11](fp_moves/CANDIDATE03_REVIEW.md): genuine e16/m1/op6 source point plus three start/VL controls and seven integer/stored-EEW derivatives, all PASS. Four measured BE0 failures repaired; seven baseline-passing complete traces unchanged. Not the full21504-case original op6 partition. |
| N | [M3 representative16](fp_moves/CONTROLS16.md), [terminal JSON](fp_moves/candidate03_controls16_01/complete.json): ten M2 smokes and exactly A's six singles, unchanged ELF/oracle, all PASS. All16 complete cycle traces identical to M2, 310350 event rows; 1305 pins unchanged. jobs2,470.72 wall seconds, no build. Does not include A's combined program or all38. |
| O | [M4 independent35 audit](comparison_alias_original/candidate04_audit02/README.md), [terminal finding](comparison_alias_original/candidate04_audit02/finding.json): exact19 archived comparison-alias singles plus10 smokes and6 singles, complete full-oracle PASS/exit0; staged ELFs match,1859 plan pins/1144 original-measurement pins/107 original-source pins unchanged. All16 CSVs are complete;15 byte-identical to M3. restart_compare has1374 cycle-only row differences, each+1, final30318->30319; noncycle fields all match. Three separate new FP controls remain a different evidence set. |
| P | [M4 NV8 report](comparison_source_controls/nv_successor/DUT_REPORT.md):8/8 new directed controls PASS on the same image, host464 checks/Spike8 PASS first,701 pins unchanged. Distinguishes active sNaN/qNaN from prestart/inactive/out-of-stream tail and checks nonperiodic data, full destination and CSRs; e16/vv scope only, no historical whole-program claim. |
| Q | [M4 scalar19 independent audit](comparison_scalar_original/terminal_audit01/README.md):19/19 archived scalar-comparison single-source ports PASS, original full oracle and exact VMSEQ.vx allocation/retirement/completion;1321 plan pins,166 source pins and539 frozen sources unchanged. No full4032-case parents or original Linux binaries. |
| R | [M4 gather terminal](gather_original_review/successor01/vcs_candidate04_remaining7_01/complete.json):eight exact source tuples PASS across one retained independently accepted control and seven new runs. Only empty selection-loop bounds shortened; original RNG, setup, target assembly, full-capacity oracle, guards and vstart preserved. Old TIMEOUT/CANCELLED and worker NOT_ACCEPTED remain. Not all83 historical records or11 stalls. |
| S | [M4 NF8 selected4 terminal](masked_translation/nf8_strided_review/sv39/vcs_candidate04_01/complete.json):trials19/17/67/31 PASS,12394 checks, real Sv39 load/store fault/retry and all-off contract. Source-derived original geometry, not full192 tuples or Linux signal/sigreturn replay. |
| T | M4 unchanged38 replay [terminal result](integration/candidate04_regression38_03/complete.json): **38/38 PASS**, completed2026-10-11 04:02:49 -07:00; service `ara-candidate04-arithmetic38-03` inactive/dead, Result=success, exit0. Parent independently rechecked1368 pins, actual38 private ELF/image identities, exact membership, zero returns and76 console/VCS logs with oracle markers and no raw failure markers. Preserves K's ELF/oracle/budgets. See [terminal audit](integration/CANDIDATE04_38_TERMINAL.md); no broader original22-shape or Linux claim. |
| U | [Whole-register1134 preparation and live replay](whole_register_original/README.md): original source/header/assembly identities checked; full1134 and20 disjoint partitions pass Spike. Six M4 simulators started under `ara-whole1134-candidate04-01`. DUT acceptance pending; partitions preserve tuples/oracles but not the full original predecessor-vtype history. No Linux or continuous-program DUT acceptance implied. |
| V | [NF8 full192 reference terminal](masked_translation/nf8_strided_review/sv39_full192/reference_campaign01/complete.json): `HOST_SPIKE_ALL192_PASS_NOT_DUT`, exact trials0..191 in48 groups. This establishes software-reference readiness only. The jobs8 successor requires full CSV-checker validation and reviewed preflight before its serial pilot and remaining DUT groups. |
| W | [Remaining75 Gather terminal](gather_original_review/remainder75_01/vcs_candidate04_01/complete.json), complete SHA `9b71c95ad9df4e32beb84d88407c40ff5368bfb311bdfa6ae4897de7afd551f6`: **75/75 PASS**, independent raw validation matches the stored result;3972 pins,150 logs,75 CSVs,7792 full-capacity reads and150 guard reads checked. First12/remaining63 and worker returned0 without error; no owned service/cgroup/simv remains. Journal access denied, so no journal-exit proof claimed. Together with R these establish83 unique source singles, not whole parents or11 historical stalls. |
| X | [NF8 full192 independent DUT acceptance](masked_translation/nf8_strided_review/sv39_full192/terminal_resume20261011.md): frozen M4, exact trials0..191 in48 four-case programs,594288 comparisons,11193408 checkpoint bytes,144 expected faults and48 all-off no-fault cases. All48 complete CSVs reread;726 pins unchanged. Original Linux signal/context paths and continuous192-process history remain separate. Historical outer-service exit was not recoverable after collection; actual child results and architectural completion are checked. |
| Y | [Original arithmetic-prefix terminal audit](arithmetic_restart_original/TERMINAL_AUDIT01.md): five prefixes56/38/56/56/56,262 original calls, M4 PASS;124928 result elements,524 guards,10 logs and992 pins independently checked. Plan SHA `34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4`. Recovered C rebuilds all22 original Linux ELFs byte-identically, but these five prefixes are neither the full22 matrices nor recovered original C text. |

Additional completed evidence: [FP08 independent terminal recheck](fp_comparison_original/TERMINAL08.md)
accepts two original masked/unmasked e16/m2 comparison prefixes on M4,130 calls
each,260 targets total. Complete data/flags oracles, both CSVs, private ELFs and
2750 pins pass; no abort and both runners exit0. Measured elapsed1647.31/1633.25s.
The682-call alias prefix remains unexecuted; these results do not close full
parents or all942 prepared calls. Parent observed service inactive/MainPID0/
Result=success/ExecMainStatus0 before collection; the later independent audit
could not recover that numeric service exit independently from the journal.

## Every Failed-Record Family

VCS below means a real instruction/VRF/translation-capable source port can test
the RTL contract. It does not mean the archived unmodified Linux ELF has run.

| Original family / records | Current fix and exact measured scope | Remaining work / required environment |
| --- | --- | --- |
| RVV-03 whole-register move /2 | Dispatcher architectural-vstart/EEW conversion; A `wholemove` genuine selected source, B mixed-layout/dependent-read controls PASS on F4 and M2 via K | Remaining parent/detail trials can be source-ported in VCS. Original ELF closure needs Linux/board replay. |
| RVV-04 protected-page/FOF /8 | M2 AddrGen predicate-qualified translation, VLDU fault drain, fault-only load completion barrier; H all-off scenario3-derived suppression and active control; I FOF shortening/masked suffix PASS | Not every exception scenario/width or Linux fault handler covered. Further real-Sv39 VCS is meaningful; signal frame/sigreturn and original permission semantics need Linux/board. |
| RVV-05 widening FP reduction /1 | m8 reduction legality fix; A original e32/m8 VL0 `m8widen` PASS, B ten nonzero-VL ordered/unordered controls PASS on F4 and M2 via K | VL0 legality is not nonzero arithmetic proof by itself. Full original matrix remains distinct. |
| CAP-01 misaligned segment preparation /9 | No target-segment bug established: historical ordinary preparation load faults before target | Retain capability/setup classification, not repaired segment coverage. Reproduce exact preparation/OS signal only if pursuing this record; do not substitute aligned target tests. |
| RVV-07 sparse ordered reduction /11 | Selected-element exception-mask coordinates fixed; all11 selected singles accepted. Additionally, [e16/mf4 full6720 M9 independent terminal review](ordered_reduction/full6720_e16_mf4_vcs_m9_plan01/TERMINAL_REVIEW.md) accepts complete contiguous history,144-byte oracle per call, flags/vstart and required owners; simulator/service/collector actual0 | [Original11 inventory](ordered_reduction/original11_inventory01/REVIEW.md) confirms11 archived shape records, not11 roots. One full6720 source-port parent is now accepted; the other ten complete parents and original Linux execution remain unclosed. Singles and166 module points do not close those scopes. |
| RVV-08 large-offset slide /3 | Exact nonzero MaskM-word RAW completion constraint; E six original-source programs PASS on F4 and M2 via K, including all-on and preceding sparse/all-off sequences | Do not merge this with restart starvation. Original board identities still need deployed-image replay for board closure. |
| RVV-09 nonrestart FP compares /208 | Per-element NV carried to MASKU and qualified at accepted active window; D selected flags ports/matrices PASS on F4 and M2 via K | Flags repair does not close independent data symptoms or208 whole ELFs. Broader original-source VCS possible, original oracle provenance must be retained. |
| RVV-09/11 restarted FP compares /29 | Existing old-vd origin correction, full mask stream, exact NV window and queue descriptor guard address distinct contracts; D PASS on F4 | Unmatched e16/m8 unmasked-v8 original64-data-error symptom remains open: isolated and reconstructed50-call prefix passed historically. Preserve original sequence/Linux-board evidence; no proven current cause. |
| RVV-10 FP moves/slides /49 | [Original tuples recovered](fp_moves/SELECTION.md): 47 numerical partitions plus two parent/detail records. M/N focused and representative controls remain separate; [all47 archived single-source ports](fp_moves_original47/README.md) now PASS on M3:32 slides (op2/3/4/5) +15 scalar insertions (op6), all15 original shapes, unchanged oracle. [Independent terminal postcheck](fp_moves_original47/terminal_audit01.json): exact47 COMPLETE/PASS/exit0, exact markers/counts, failure-marker veto,1309 pins including539 frozen sources unchanged | Acceptance covers the47 archived measured singles, not their full21504-case parent matrices, the two overlapping parent/detail records, or original Linux binaries. Original full-sequence/OS closure remains distinct; no other FP operation or whole-family closure inferred. |
| RVV-12 scalar comparison restart /19 | Packed old-vd zero-origin correction, full mask stream and M4 comparison-source origin. Q independently accepts all19 archived singles on M4, spanning fractional LMUL through m8 and all SEWs | Full4032-case parents and original Linux execution remain distinct; do not infer one common cause for all historical symptoms. |
| RVV-13 aliased comparison restart /19 | All19 genuine source singles pass Spike. M3 selected e16/m1 and e8/m1 pass; e8/m2 fails at active bit84. Actual source addresses start two lane words late while MASKU compression starts at0; source148 explains wrong bit84. M4 lane-source correction has independent19-single PASS plus16 representative controls (O) | Preserve M3 FAIL/CANCELLED and original agnostic oracle; mask-logic alias PASS is a different family. Original4032-case parents and Linux execution remain unaccepted. |
| RVV-19 gather numerical /83 | R's eight authentic source tuples plus W's75 independently accepted source singles establish83 distinct source ports PASS on M4. The earlier timeout was after target/oracle completion in empty scalar enumeration; a separate startup-observer failure is preserved. See the independent terminal audit in `gather_original_review/terminal_audit75_01.md`. | Full parent sequence/predecessor-state coverage and11 historical stalls remain open.83 passing source singles do not establish original Linux program acceptance; no new RTL hang proved by the old timeout. |
| Unit/strided/segment fault replay /429 | Three M2 memory fixes accepted by H/I/J; X independently accepts all192 source-derived NF8/e32/mf2 positive-stride Sv39 tuples on M4 with full-memory and fault/retry checks; M6 independently accepts all40 archived NF2 failed-single geometries plus two separate J4 positive controls | NF2 full96 parent, other NF/SEW/LMUL and original Linux sequences remain separate. Original NF8 169-versus128 error difference remains unlocalized; the outstanding difference is Linux signal/context behavior and continuous process history, not missing192 Sv39 geometries. See [scope review](masked_translation/nf8_strided_review/nf8_remaining_scope_review01.md). |
| RVV-15 indexed NF7 replay /1 | No indexed-specific root cause/fix claimed. Current M6 independently accepts all96 original source-derived trials/24 CSVs (284816 checks,168 checkpoints,72 faults,96 ecalls), with1973 pins unchanged and actual audit wait0; earlier frozen M2 `vcs_plan06` original96 source-derived trials PASS; independent complete24-CSV replay confirms284816 comparisons,168 checkpoints, precise faults/retries and no timeout/abort. | Original Linux equivalence/ABI and the unidentified original failure phase remain separate gaps. Original was96 cases/72 signals/one check error. This result does not establish every archived root cause or other indexed widths/overlaps. |

## Every Stall Group

| Original group / records | Current evidence | Remaining gap / environment |
| --- | --- | --- |
| Masked slides /85 | Stream/prefix/source-origin repairs; 3648 joint module cases and A/B selected F4 ports; E addresses a different large-offset RAW issue | Not85 per-record reproductions. VCS exact source/sequence coverage remains possible; a printed boundary is not a unique accepted instruction. |
| Arithmetic/merge/compare boundary /45 | Zero-origin full MaskM stream repaired; real-lane/MASKU41-case contract suite, A selected compare and D compare matrices | Not complete vmacc/vsmul/vfmerge/alias original programs.33 printed VL512/start256 records and12 merge records without final trial remain distinct. K is selected integration regression, not closure of45. Recover trial, then VCS. |
| Mask-logic source alias /3 | MaskM source exemption already present; [M2 bounded terminal acceptance](mask_alias_original/BOUNDED.md): tuple3/3 and prefix3/3 PASS, exact original prefixes0..97/0..65/0..97 plus their repeated exact tuples. [Strict independent checker](mask_alias_original/terminal_audit01.json) confirms both stages COMPLETE, exact six names/counts/raw markers/exit0, failure-marker veto and unchanged pins; supersedes the earlier ongoing-alias status | 262 distinct original trials,265 calls including tuple overlap. Full5376-case parent matrices were not replayed on DUT; no whole-family, original Linux or M3/candidate03 closure. PASS of the measured-source prefixes does not itself prove a historical internal root cause. |
| Gather variants /11 | Stream repair relevant; C numeric prefix acceptance is separate. Out-of-range response gating existed in deployed RTL, not a new repair | Exact last trials missing. Recover sequence/acceptance first; then VCS distinguish mask starvation from request/data token accounting. No stall closure from BE fix. |
| High-end extension overlap /42 | Precise integer-extension classification and source snapshot for masked/unmasked conversion; F genuine VL127 plus vf2/4/8 matrices PASS on F4 and M2 via K | Not all42 original ELFs. Trial22 whole-store timeout suspicion was not proven livelock; same-image full matrices completed. Other exact overlap sources can run VCS. |
| Kernel vector CSR wait /3 | M2 VLDU drain and fault-only barrier repair measured internal completion defects; H/I/J pass selected fault/retry paths | No exact kernel CSR wait reproduced/closed. Original Image/vmlinux, signals and vector-state handling require Linux/board; use VCS only after extracting a justified internal trigger. |
| Segment alignment boundary /9 | J proves four NF2 fault/retry contracts, not these historical phase-marker/vlseg3 boundaries | Acceptance, VL/mask/alignment and preceding phase-store fault still uncertain. Recover original Linux scene before claiming target issue; real-Sv39 port only after exact geometry known. Separate from CAP-01's nine preparation failures. |

## Supplemental And Excluded Scope

| Item | Disposition |
| --- | --- |
| RVV-01 indexed width/overlap/fault (outside three inventories) | M5 measured mixed-index EEW normalization cancelled by dedup; M6 retains the required source conversion and existing snapshot/replay path. Three full source-faithful Sv39 programs and representative48 have independent acceptance; details are in the latest-repair section above | Original Linux scheduling, signal/retry ABI and deployed-board replay remain open. Do not merge this overlap root with disjoint-register NF7 or infer all429 fault records are closed. |
| RVV-02 original arithmetic restart matrix (outside198) | Complete source-port union18/22 shapes,86940 calls independently accepted across frozen images; e32/m4 full5985 is the latest M9 addition. Remaining4 shapes/20160 calls are e8/m8,e16/m8,e32/m8,e64/m8. This is not K's38 integration ELFs, all22 on M9 or original Linux/historical-stall closure. |
| Unordered reduction NV and activity epoch found during integration | Additional measured fixes, not invented871 inventory buckets:80/166/606 local regressions,432 epoch cases; F4 B/G programs PASS, and the same programs now PASS on M2 via K. |
| MASKU full result-queue descriptor overwrite | Independently measured address96->98 while full/noaccept; full guard repaired and24 consumer cases passed. D is integrated follow-up, not proof of every comparison data symptom. |
| 47 mixed /124 unexecuted; TEST-01..07, REF-01, observer/loader races | Not automatic RTL defects.20 memory observation gaps later passed exact-ELF historical retest; others retain mixed history. Unexecuted children have no failure result. Preserve handler/oracle/capability/reference exclusions; do not count as fixes or acceptance. |

## Remaining Work, In Order

Completed since the initial audit: K arithmetic38 **38/38 PASS on M2**;
M focused11 and N representative16 **PASS on M3**. N rehashed1305 pins,
including both frozen snapshots, and compared every byte of all16 cycle CSVs.
This closes the selected same-image regression gaps, not the historical full
arithmetic family. NF7 now has independent96-trial acceptance on M2; mask-logic alias has
six-partition terminal acceptance. Comparison alias has a new measured source-
origin defect and independent19-single/16-control acceptance on frozen M4 (O),
not whole-parent or Linux acceptance.

1. Retain **NF7 aggregate DUT** acceptance strictly on frozen M2. Evaluate
   current-image regression separately; do not label M2 data as M4. Original
   Linux equivalence and the historical cause remain separate questions.
2. Close exact-source gaps for alias compares/mask logic, large-group
   arithmetic/merge, gather stalls, remaining FP move/slide operations and
   unmatched comparison data. Most are VCS-portable once the exact source
   sequence/final trial is recovered; do not invent shared root causes.
3. Extend real-Sv39 coverage only against selected genuine remaining memory
   records (other widths/NF/stride/FOF/partial fields), retaining full oracle.
   NF2 or NF7 results do not establish all429 replay records.
4. Separately authorize **original unmodified Linux/board ELF replay** with
   new deployed image identity for signal frames/sigreturn, permission versus
   unmapping, kernel vector CSR/context cleanup, ambiguous segment boundaries,
   and original parent sequences. No current source-port result replaces this.

Audit limits: the initial NF2 audit rechecked664 input/image/source files.
Subsequent K and M have linked independent audits; N freshly rechecked1305
plan pins and all16 actual outputs. These are scoped evidence audits, not a
fresh871-record replay or blanket historical closure. This update also revises
the root README under parent authorization; NF7/alias owner artifacts are unchanged.
