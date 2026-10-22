# MACC Selected Boundary Terminal Audit, 2026-10-11

## Verdict and Scope

**Independently accepted: `PASS_2_MACC_SOURCE_SELECTIONS_M4`.** Read-only
postcheck of `candidate04_run01`; no simulation, helper execution that writes
terminal artifacts, RTL edit, or original-log edit was performed.

This covers single original trial481 and the immediate original480->481 pair:
three calls, **two unique original trial positions**, not the full482 prefix,
the full22400 matrix, all12 MACC records, or original Linux/board closure.
The single omits vector history0..480; the pair omits0..479 and retains the
original destination initialization between calls. No earlier PASS is used to
substitute for these actual M4 results.

## Independently Checked Evidence

Read `candidate04_plan01/plan.json`, `candidate04_run01/{attempt,launch,complete}.json`,
and `candidate04_run01/replay/{run,summary}.json`, both actual private inputs,
commands, raw logs, complete CSVs, and stored trace audits. A separate read-only
Python scan reconstructed source RNG/arithmetic and compared actual scalar
loads, rather than trusting only the runner's PASS or stored expected arrays.

- All821 plan pins,12 terminal raw pins,18 predecessor fixed-gate pins, and
  referenced image files matched. Private ELFs matched their prepared sources.
- Exact two expected names: COMPLETE/PASS, simulator return0, empty failure
  reasons. Results and summary agree; terminal `aborted=false`,
  `pins_unchanged=true`, no error.
- Four raw logs, console and `work/run.vcs.log` per case: exact source-count,
  selection and board markers; one simulator success and `$finish` per log;
  no failure, unsupported, trap, fatal, assertion, cancellation, interruption,
  or timeout marker.
- Both CSVs: monotonic cycles, contiguous retirement order, no retired traps;
  exact13 original instructions per call, addresses and arguments, original
  scalar load0, VL512, vstart1/256, rounding mode0, returned vstart0.
- Independently checked1536 element reads and6 guard reads, each expected
  address once per call. Original old destination0; active result
  `(a[i] * b[i]) & 255`; prestart remains0; guards0x5b. Recomputed call audit
  agrees with the stored `macc_trace_audit.json` and terminal audits.
- Trace summaries match full scans; CVX exception count0. Each trace reaches
  actual success CTRL store at0xd0000000 with data0, followed by six `a001`
  self-jump retirements, rd0 and no memory effects. Parking is not treated as
  premature failure or as the only evidence of success.

| Case | Calls | Elapsed seconds | CSV rows | Retired | Last cycle | CTRL0 cycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| macc_e8_m4_single481 | 1 | 2209.667120 | 1933838 | 1933781 | 2288143 | 2288134 |
| macc_e8_m4_pair480_481 | 2 | 1701.854638 | 1391058 | 1390956 | 1789474 | 1789465 |

Target is `vmacc.vv v24,v8,v16,v0.t`, opcode `b5042c57`.
Single481 helper begins2252946, target2253123, ends2256241.
Pair480 begins1694970, target1695145, ends1698263; pair481 begins1751740,
target1751909, ends1755027. All are seed0/op0, e8m4, VL512, all-on mask,
original zero accumulator and exact source oracle.

Runner start2026-10-11T05:41:32.876102-07:00; completion06:19:10.404324-07:00;
runner wall2257.528222s. Attempt-to-terminal2279.427234s is below the7800s
outer limit; each case is below7200s. Recorded service properties are
`ara-macc-boundary-candidate04-01.service`, `RuntimeMaxUSec=2h 10min`,
`KillMode=control-group`. This resume did **not** acquire independent systemd
terminal exit/journal evidence; simulator exit0, COMPLETE and no-abort are
independently established, not inferred from a missing/inactive service.

## Exact Identities

| Artifact | SHA256 |
| --- | --- |
| plan | `96b6aa302176fda36d2b684b00c8df3e136e172e9b1c62b65cac4bff72326a58` |
| complete.json | `3c61b3e341865b5ba39718ca663cf587db9e037099e0f02bccfa15a068076587` |
| replay summary.json | `e1df0acb03a6da3843c10bd7f2988849ac9c928aba45e136c35b2135ec96eb22` |
| frozen runner | `1f2de736a5023aec636d24de05521ebdb25208a2c24a28ae71daa28fd1f751b2` |
| M4 image.json | `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673` |
| single481 actual ELF | `fba12e5cea7ec8f31b8189c7ff724a7cbc948da840a224c647ed6b57f9df4285` |
| single481 CSV | `c181e31e092cbe713d6177fb2c255395bc502ce90e65f6c3f73a6c04bdd4b837` |
| pair480_481 actual ELF | `53d6b25ae90f8fc83517c23f03c9e7e736d77a6ecfe83e9449c5ee60a22d33fc` |
| pair480_481 CSV | `f02851bf04b4901364856774a3f859c9fd59fc6261e36fef508a04c8689d5fb6` |
| archived Linux ELF | `608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d` |

Image: `/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`.
Original child: `rvv_integer_macc_accumulators_restart_e8_m4`.
`identity02` proves byte-identical whole archived ELF reconstruction using
successor C plus original assembly/header/compiler; the original C text hash
was not recovered. Preserve this distinction. See `SELECTED01.md` and
`LAUNCH_PLAN01.md`. Full482 software reference remains16,438,522 Spike
instructions and has no corresponding DUT acceptance here.

## Remaining Original-Scope Priority

Read-only comparison used `../../CURRENT_SCOPE.md`, the root README/reports,
`../NEXT_ORIGINAL_SCOPE.md`, and original
`/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/{ALL_FAILURE_REVIEW,STALL_TRIAGE}.md`.
Do not read the871 numerical records,198 stalls, or45 arithmetic/merge boundary
records as one root cause or one acceptance set.

1. **First: actual M4 gather ei16 numerical counterexample.**
   `../../gather_original_review/stall_prefix2_launch02/vcs_candidate04_01`
   records ops20 FAIL, rc255,2063.828487s and the actual raw line
   `op=20 seed=0 scalar=0 vl=256 mask=0 element=128 vstart=128 expected=79 actual=0`.
   The paired ops1 job was cancelled by fail-stop, not proven numerically bad.
   This differs from launch01 startup/parking rejection and from83 accepted
   small gather singles. Prepared source ordinal66 (zero-based row65), tuple
   `[0,20,0,4,0,1]`, has `indices16[128]=511`, VLMAX512, `input[511]=79`.
   The shifted index256 is513, predicting zero under the origin mismatch.
   Use that exact source/setup/oracle first; preserve prefix or explicitly
   label any single extraction's missing history. Existing raw failure is
   genuine, but current root cause still requires cycle evidence. Independent
   RTL chain/probes are recorded in `../../gather_repair05/STATIC_REVIEW.md`.
2. **Next unmatched FP comparison history/data domain.**
   `../../fp_comparison_original/prepared02` contains the held
   `alias_v8_e16m8_prefix682`; archived reconstructed whole Linux ELF SHA
   `266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
   Original call50 op0/seed0/VL512/mask0/sticky1 reported64 errors with
   flags17/17; isolated and50-call prefix passed historically. Preserve
   intervening vv/vf/operator/layout history rather than declaring this the
   all-off NV issue. The prepared682 additionally reaches original681/682
   op2/seed1/VL1/mask0/sticky1 historical flags1->17. The accepted130+130
   prefixes do not cover682. Budget review is needed before any long launch.
3. **Untouched mechanism: RVV-01 indexed width/overlap/fault.**
   Original `width_restart04_live.json` records `d32m2_i64_fault_ov1`
   exit139/badaddr0x0000c03fba460000/PC0x1045a, while corresponding resident
   ov0/ov1 and fault ov0 controls passed. Recover their exact source/ELF
   manifest and fault mapping before porting the quartet to real Sv39;
   `vector_width_probe.c/.S` and original width-fault reports are the entry
   points. This report does not establish new ELF pins for that next task.
   Disjoint-register NF7 cannot close overlapping-index preservation, and
   bare-metal trap success cannot by itself close Linux SIGSEGV/sigreturn.

Do not rerun already accepted sets as discovery: M4 arithmetic prefixes262
calls, original gather83 singles, comparison-alias19, scalar-comparison19,
FP08 two130-call prefixes, unchanged integration38, M3 FP-move47 singles,
M2 mask-alias262 unique positions, fixed selected2 and these MACC selected2.
Whole-register1134 configurations have partitioned acceptance; the remaining
59 prepared adjacency pairs are history coverage, not a newly measured bug.

The scope ledger still describes some work as running/unexecuted. New terminal
artifacts also report `PASS_ORIGINAL_VFMERGE_PREFIX195_M4` and
`CANDIDATE04_NF8_FULL192_PASS`; their statuses were read, **not independently
re-audited in this resume**. Consult their owners' terminal audits before
claiming closure, but do not schedule duplicate discovery runs on stale scope
text. No root README or CURRENT_SCOPE row was edited.
