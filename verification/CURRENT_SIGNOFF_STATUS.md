# Current RTL Verification Signoff

Status date: 2026-09-26. This is a running evidence index, not a claim that
the complete RTL has signed off. FPGA/board validation is outside this phase.

Verification ownership is now consolidated in this branch; see
[CONSOLIDATION.md](CONSOLIDATION.md). The consolidation changes test sources,
host tooling and environment ownership, not RTL. Imported tests are not new
RTL PASS records. New failures stop the campaign pending user instructions.

## Seed 509 Stop and Authorized Repair

Checkpoint `coverage-checkpoint-20260926-02` stopped after 19 new random cases
passed and `short-memory-509` reported `RTL_STALL`. Ten functional cases were
not completed. The coverage build was cancelled; this checkpoint supplies no
new coverage percentage. Its service has exited and preserved first-failure
evidence. The user subsequently authorized repair of this failure.

Two bounded runs of the unchanged image isolated premature architectural
acceptance of a segmented store: the first field completes, but dispatcher
waits for the aggregate response after withdrawing further field requests.
The repair excludes the registered segment reservation from ordinary-store
early acceptance and adds a verification assertion. Ordinary and whole-register
store acceptance is retained. Fresh-image functional/performance validation
is pending; see [cycle-level diagnosis](SEED509_SEGMENT_STORE_DEBUG.md).

## Bounded Checkpoint Started 2026-09-26

After the [fail-fast preflight repair](FAILFAST_REPAIR_20260926.md), the service
`ara-dsa-coverage-checkpoint-20260926-02.service` was started with an enforced
control-group cleanup boundary and no automatic restart. Its live state and
first failure are in `out/coverage-checkpoint-20260926-02/` (`checkpoint.json`,
`functional-scheduler/status.json`, and `STOP.json` within the failed scheduler).

- 20 new short random cases: control-cross and memory-cross, seeds 501-510.
  Each requests 300 generated instructions; signatures and scaffolding add
  instructions, so this is not the total retired instruction count.
- Five frozen random representatives: arithmetic, load/store, FP32, FP64,
  and vtype churn. They must pass again on the current VCS image.
- Five directed cases: illegal vstart, mask destination overlap, illegal
  register groups, widening overlap, and narrowing/rounding edges.
- Up to five first-stage workers, initially four random workers plus one
  incremental Verilator coverage build. Random checks require complete
  independent scalar trace/vector-writeback matching against Spike with Zvfh.
- Only after the functional stage passes, replay 14 selected cases with three
  coverage workers and merge the same-image results. The scope is line/expression
  coverage, not toggle, separate FSM, or assertion coverage.

This entry records startup, not completion or a new coverage percentage. No RTL
was changed for this checkpoint. Any non-PASS stops the campaign for user review;
timeout, checker failure and RTL mismatch must be distinguished before diagnosis.
Long-running jobs are left in the background rather than continuously polled.

## Current Integration

The store/FP candidate is now in this worktree, including precise B faults,
request-buffer empty bypass, FP16/INT8 conversions, floating-CSR ordering and
DIV exception-format/mask handling. Existing illegal-register-group checks,
random profiles and the Verilator tohost monitor were retained. CVA6/FPnew
are independent dependency copies with regenerated patch hashes.

The source candidate passed all 21 regression tasks and the additional
52-case/1612-check DIV test. The merged image compiles with 457 source inputs
verified unchanged; all seven post-merge smoke tests PASS, including the
retained illegal-register-group/mask-overlap checks. Evidence is in
`out/merged-store-fp16-smoke-20260926-01/`. AXPY remains 2810 cycles, versus
2786 in the original imprecise baseline: steady-state throughput is restored,
but the total-cycle no-regression gate is still open (+0.86%).

The earlier 70-case and coverage results below describe their frozen images,
not this merged RTL. They must not be relabelled as coverage of the new image.
See [repair and integration details](STORE_B_REPAIR_CHECKPOINT.md).

## Previous Checkpoint (2026-09-25)

| Gate | Current evidence | Remaining risk |
| --- | --- | --- |
| Bounded RVV VCS/Spike | 70/70 strict-audited random cases across six profiles on `out/integrated-wred-m8-build-20260925-01/sim/`; their 70 frozen ELFs have 70 distinct SHA-256 hashes; five state/layout directed cases pass | Three of 15 control-cross programs still disagree on FP16-to-INT8 narrowing |
| QBS/AKV functional smoke | One handoff case passes on the same VCS image; separately, 10 QBS/RVV pairs plus one AKV/RVV pair pass the rebound source audit | Handoff is a self-check, not Spike full-state equivalence; paired programs still need final-image coverage replay |
| Final-RTL code coverage | Line/expression image rebuilt with a C++ tohost monitor; one audited memory-cross replay is running under `ara-dsa-tohost-coverage-preflight-20260925-01.service`. Earlier retries were stopped after the missing random-program completion monitor was identified. The separate toggle-only image is still building | No final-image percentage or toggle result yet; monitor compilation/unit checks are not a passing RTL replay |
| AXI store B fault | Isolated precise candidate passes multiburst fault and UVM checks; source-matched AXPY A/B is 2786 versus 3193 cycles | +14.6% cost is unacceptable; no RTL fix merged |
| Full VCS Linux | Stopped by request | No full-boot PASS claimed in this campaign |

The corrected VCS image manifest and the pending line/expression Verilator
manifest have 190 shared Ara/CVA6 source paths with identical SHA-256 hashes;
this includes all 49 `hardware/src` paths listed by Verilator. The VCS
filelist also names `accel_dispatcher_ideal.sv`, but its
`IDEAL_DISPATCHER` branch is not enabled for this real-dispatcher campaign.
This checks shared source identity, not equivalence of simulator elaboration
or execution. `source_manifest_tohost.json` records the 509 inputs after the
C++ harness fix. The earlier manifests are retained as historical records;
their C++ harness hash no longer matches the working source. Final-image
coverage remains pending.

### Coverage replay completion correction

The 600-second memory-cross attempt was initially attributed to a short wall
limit. Its longer retry reached the program's terminal path and then kept
executing the tohost loop. Unlike the VCS commit monitor, the Verilator C++
harness did not consume `+COMMIT_TOHOST`; the control-register exit alone
cannot terminate these riscv-dv ELFs. Increasing the timeout cannot fix that.
The four incomplete coverage replays were stopped with their artifacts kept.

The harness now reads the test's 64-bit tohost location in simulated RAM,
requires its initial value to be zero, accepts value 1 as PASS and reports
other nonzero values as FAIL. `run_directed_coverage.py` obtains the address
from the independently audited source run's structured VCS command, and
the coverage runner records/forwards it. Only `ara_tb.o` and the executable
were rebuilt; the generated RTL objects were reused. The single preflight
uses the frozen `ara_dsa_rvv1_short_memory_cross_0` ELF, a 30,000-cycle bound,
and a 3,600-second wall limit in
`out/integrated-tohost-coverage-preflight-20260925-01/`. This entry records a
running experiment, not a completion or coverage improvement.

## Focused coverage and store-fault campaign, 2026-09-25

- The long `loglevel=3` VCS Linux boot was stopped at the user's request.
  Its partial log is preserved at
  `out/integrated-linux-lean-l3-soc-20260925-02/`; it is not a boot PASS.
  This campaign now prioritizes bounded directed/random tests and measured
  RTL coverage rather than another full Linux simulation.
- `ara_dsa_rvv1_short_control_cross` and
  `ara_dsa_rvv1_short_memory_cross` add two bounded riscv-dv profiles with
  300 requested instructions per generated program. Their one-seed
  preflights at `out/integrated-random-short-{control,memory}-preflight-20260925-01/`
  passed VCS/Spike terminal and vector-commit comparison plus an independent
  frozen-input audit. All four isolated five-case memory-cross batches passed
  strict independent audits (20/20). The control-cross batches are not closed:
  seed 101 is incomplete, and the other batches contain first mismatches.
  One mismatch disappears when the Spike reference enables `Zvfh`, matching
  the RTL's FP16 capability. A remaining frozen case traps in Spike at
  `vmfgt.vf v18,v16` with LMUL=4 because the mask destination overlaps the
  source register group, while the RTL continues. These cases require a
  legality-focused regression and must not be counted as passing legal-stream
  random tests. The optional `--spike-isa` replay setting records the reference
  ISA used for each replay.
- The control-cross mask-compare mismatch has a focused reproducer,
  `rvv:vmask_dest_overlap_illegal`: with e64,m4, `vmfgt.vf v18,v16,ft4`
  partially overlaps its mask destination and source group. The frozen ELF
  fails on the original final image (zero traps) and passes after a narrow
  dispatcher legality check; its independent trace audit also passes. Three
  neighboring directed tests (mask compares, legal widening overlap, illegal
  vstart) passed on the repaired image. The first repaired image used the
  default 1 MiB/no-QBS/no-AXI-delay build and its cycles are not comparable
  with the original 2 MiB/QBS+AKV-v2/AXI-delay UVM image. A matched image at
  `out/integrated-mask-overlap-matched-build-20260925-01/` passed the focused
  test and independent audit; the same AXPY ELF ran in 2755 cycles on both
  this image and the original image.
- The other two control-cross first mismatches were reduced to
  `rvv:vregister_group_illegal`: the original image fails to reject a
  widening operation with EMUL > 8 and an extension with a forbidden low
  source/destination overlap. The repaired RTL rejects both while retaining
  a legal high-overlap extension. The matched QBS+AKV-v2, 2 MiB, AXI-delay
  image is `out/integrated-register-group-fixed-build-20260925-01/`.
  `rvv-state-layout-gap` passes 5/5 with independent trace audit PASS, and
  the same AXPY ELF remains at 2755 cycles. Four isolated batches under
  `out/integrated-final-memory-replay-{101,201,301,401}-20260925-01/`
  replayed the 20 previously passing frozen memory-cross ELFs on this newer
  image: all 20 passed, and each five-case batch passed its independent
  trace, vector and full-match audit. This proves those frozen cases on this
  matched RTL image; it does not close the control-cross profile or code
  coverage.
  A frozen control-cross replay now gets past the original mask-compare
  mismatch but exposes a later widening-reduction legality discrepancy.
- A new `rvv:vstore_axi_error_bursts` test uses a strided vector store to
  produce eight AW/W/B bursts for one instruction. The final integrated RTL
  fails to take the expected store access fault. The isolated B-response
  candidate passes the program and real-DUT UVM contract, with `aw=b=8`,
  one architectural exception and no outstanding B response. This verifies
  multi-burst ownership but does not resolve the measured 14.6% AXPY
  regression; the candidate remains unmerged.
- One additional passing final-image Verilator replay,
  `rvv_vstore_mask_tail_edges`, was merged into a new 15-case coverage set at
  `out/integrated-coverage-pass15-store-mask-20260925-01/`. Independent merge
  integrity is PASS. DUT-hierarchy hit points rose from 20,388 to 20,573 of
  38,601; source-filtered hits rose from 10,370 to 10,551 of 23,436. This is
  an incremental measurement, not coverage closure. Two more passing directed
  replays, `rvv_vmask_mem_emul_edges` and `rvv_vunit_vstart_edges`, were then
  added to the independently audited 17-case merge at
  `out/integrated-coverage-pass17-memory-vstart-20260925-01/`. Its hit counts
  are 20,678/38,601 by DUT hierarchy and 10,649/23,436 by source filter.
  A fourth directed replay, `rvv_vpolicy_masked_edges`, was added to the
  independently audited 18-case merge at
  `out/integrated-coverage-pass18-policy-20260925-01/`. Its hit counts are
  20,686/38,601 by DUT hierarchy and 10,657/23,436 by source filter. A
  frozen, strictly audited 300-instruction memory-cross program was replayed
  under Verilator in `out/integrated-memory-cross-coverage-20260925-01/`, but
  the old-image run was stopped before completion after the dispatcher fixes.
  Its partial output is not coverage evidence and is not included in a merge.
- The 18-case Verilator coverage set predates the two dispatcher legality
  fixes. It remains useful as a gap map, but is not final-image coverage.
  A final-source line/expression Verilator image is rebuilding incrementally
  under `ara-dsa-final-verilator-coverage-build-20260925-01.service`; a
  separately budgeted old-source toggle image is still building. A fresh
  passing-case merge on the final-source image is required before reporting
  final coverage numbers.
  The isolated B-response candidate additionally passed one configuration-
  matched AXPY real-DUT UVM diagnostic run at
  `/home/wangwy/openproject/ara_dsa_store_fault_fix_20260925/verification/out/store-b-axpy-axi-trace-20260925-01/`.
  Its first AW, final W beat, and B handshakes occurred at cycles 485, 532,
  and 537; the store CVXIF request/response handshake followed at cycle 539.
  This supports the stall hypothesis but does not by itself establish the
  complete cause of the 14.6% AXPY regression. The candidate remains unmerged.
- The first register-group legality repair also rejected a legal
  `vwredsumu.vs` at `e16,m8`: its internal widened EMUL encodes reserved,
  although the architectural reduction result occupies one register. A
  targeted check in `rvv:vregister_group_illegal` failed on the first repair
  image and passed after narrowing both decoder legality checks to exclude
  widening reductions. The corrected image is
  `out/integrated-wred-m8-build-20260925-01/sim/`. Its five-case
  `rvv-state-layout-gap` suite and independent trace audit pass 5/5;
  frozen control-cross seed 304 passes strict VCS/Spike full-state and vector
  comparison plus independent audit. Configuration-matched AXPY remains
  2786 total cycles, the same as the pre-repair baseline.
- On that same corrected image, 12 of 15 previously generated control-cross
  programs pass full comparison. The three remaining first mismatches are
  `vfncvt.*.w` at SEW=8: Spike executes an FP16-to-INT8 conversion while
  dispatcher currently rejects it. Static RTL inspection shows the FP unit's
  INT8 format enable and 8-bit result packing depend on FP8 hardware support;
  simply relaxing legality would enter an incomplete datapath. This remains
  an architectural coverage/correctness gap, not a passing random case.
  The fourth five-program control batch (seed 101) was interrupted before
  results were generated and is not counted. A new final-source Verilator
  line/expression build is running; the old-source toggle build was stopped
  without a passing toggle result.
- The 20 frozen memory-cross programs were replayed once more on the
  corrected `integrated-wred-m8-build-20260925-01` image, in four isolated
  five-case directories named `out/integrated-wred-m8-memory{101,201,301,401}-replay-20260925-01/`.
  All 20 passed VCS/Spike comparison, and each batch's independent audit
  requires complete commit traces, vector comparison and full match. The
  20/20 count is therefore specific to this corrected image, not inherited
  from an older simulator.

## Final integration image, 2026-09-25

- `out/integrated-vcs-image-20260925-01/sim/` is the final integrated 2 MiB
  VCS image. Its 454-source manifest checks PASS. The effective HDL source
  comparison at `out/integrated-effective-rtl-equivalence-20260925-01.json`
  checks PASS against the previously tested bundled RTL overlay, but does
  not imply DPI or software identity. The frozen `load_store` seed 6 and
  `integer_stress` seed 5 strict VCS/Spike/vector audits, six directed
  cases, and the real Qwen2.5 combined QBS+AKV UVM case have passed on this
  integrated image. Seven random profiles x ten seeds have since passed strict
  independent audits on this same final integrated image.
- The historical 22-run real-data paired QBS/AKV campaign has a reconciled
  PASS at `/home/wangwy/openproject/ara_dsa_masked_indexed_fix/verification/out/final-qbs-akv-reconciled-20260925-03/`.
  That image predates three final RTL changes and is not final-image pair
  signoff. All 22 frozen ELFs fit the integrated 2 MiB image. A new
  campaign is at
  `out/integrated-final-qbs-akv-pairs-20260925-01/`; each case has an
  independent output and a frozen-input hash. Count only completed PASS cases,
  and require the
  final `audit.json` before claiming paired closure.
  The first final-image attempt reached 21/22 PASS; `q6_K/rvv` alone hit its
  3600-second wall limit after reaching about 1.477 million simulated cycles.
  The same frozen case previously completed at about 1.506 million cycles,
  so a single-worker, 4800-second resume completed the program and printed
  `Core Test *** SUCCESS ***`. Its UVM audit nevertheless failed because
  the default 100,000-event trace limit truncated roughly 174,705 request
  and response events. A further resume under
  `ara-dsa-integrated-final-pairs-q6-trace-retry-20260925-01.service` sets
  both trace limits to 500,000 without changing the frozen ELF or RTL image.
  Both failed attempts remain preserved; no final pair PASS is claimed before
  the full-trace rerun and paired audit finish.
- The integrated `rvv-corners` suite at
  `out/integrated-rvv-corners-20260925-02/` completed 35/35 self-checking
  cases on that same VCS image. Its independent
  `verification_audit_directed.json` reports PASS for all 35 frozen inputs
  and commit traces with zero errors. These self-checking cases are not a
  Spike full-state comparison. The dry-run directory ending in `-01`
  contains no executed cases and is not evidence.
  The separate `rvv-reductions` suite completed 18/18 PASS at
  `out/integrated-rvv-reductions-20260925-01/`, and its independent frozen
  input/trace audit reports zero errors. The 14-case
  `rvv-failure-regression` suite at
  `out/integrated-rvv-failure-regression-20260925-01/` completed 14/14 PASS;
  its independent frozen-input and commit-trace audit reports zero errors.
  The separate three-case `rvv-masked-indexed` suite completed 3/3 PASS at
  `out/integrated-rvv-masked-indexed-20260925-01/`, with an independent
  frozen-input/trace audit also reporting zero errors. It covers two
  masked-indexed cases absent from `rvv-corners`; it does not exercise the
  separate AXI B=`DECERR` fault contract. Its Verilator coverage collection
  is queued behind the final-source coverage image build.
- Final-image random differential replay passed a single frozen `load_store`
  preflight at `out/integrated-random-loadstore-preflight-20260925-01/`:
  strict independent trace/vector/full-match audit reports 1/1 PASS. Seven
  ten-seed profile services can now replay the 70 frozen source ELFs, one
  worker per profile, on the final VCS image; each requires its own strict
  10/10 audit. All seven profiles have completed 10/10 PASS
  with independent trace/vector/full-match audits at
  `out/integrated-random-{arithmetic,integer,loadstore,fp32,fp64,mixed,vtype_churn}-10seed-20260925-01/`.
  The offline `out/integrated-random-stimulus-audit-20260925-02.json` binds
  all 70 generated assembly sources and their frozen ELF hashes to those
  final-image audits. It records 194,029 generated vector instructions, all
  four SEWs and seven LMULs. This is stimulus coverage, not dynamic DUT code
  coverage; the exact-state random stream deliberately uses `tu,mu`, with
  agnostic policies requiring separate directed evidence.
- A separate offline retirement audit combines those 70 strictly compared
  random cases with the final-image, self-checking `vpolicy_type_matrix`
  directed case. `out/integrated-rvv-activity-union-20260925-01.json`
  rehashes all 71 frozen ELF and commit-trace records, checks one simulator
  image, and reports observed DUT-retired activity for 4/4 SEWs, 7/7 LMULs,
  7/7 memory modes, 4/4 policy pairs, and all 88/88 legal
  SEW/LMUL/policy bins. The directed case supplies agnostic-policy evidence;
  this is executed-instruction activity, not RTL code coverage or a claim
  that all RVV functional combinations have been checked.
- The final-source Verilator code-coverage image is built at
  `out/integrated-verilator-coverage-20260925-01/`. The original 49-run
  global merge plan cannot be used: three collectors encountered terminal
  timeout or self-check failures and were stopped without deleting their
  diagnostics. A separate merge of exactly 12 individually passing replays
  is independently integrity-audited at
  `out/integrated-coverage-pass13-merged-20260925-01/` (the directory name
  overstates the case count). It remains `REVIEW_REQUIRED`, not coverage
  signoff. Source-filtered coverage and DUT-hierarchy coverage use different
  denominators and must not be combined.
  The first six-case directed collector
  stopped before coverage simulation because its source PASS suite lacked
  commit traces; `out/integrated-coverage-directed-20260925-01/source_reaudit.json`
  records six evidence failures, not six RTL failures. The same-suite final-VCS
  six-case rerun with commit traces at
  `out/integrated-rvv-fast-integrity-traced-20260925-01/` completed 6/6 PASS;
  its independent audit requires traces and reports 6/6 PASS with zero errors.
  The corrected collector produced three passing replays before its separate
  matrix hit a terminal timeout. Only those three individually passing
  artifacts enter the 12-case merge; the failed `-01` directory remains
  untouched. Three short QBS/AKV cases passed final-image VCS and independent
  frozen-input/trace audit at
  `out/integrated-qbs-akv-coverage-source-20260925-02/`. Separate Verilator
  coverage replays of `app_qbs_control_smoke`, `app_akv_context_smoke`, and
  `app_qbs_akv_handoff_smoke` were started under the corresponding
  `ara-dsa-integrated-{qbs-control,akv-context,qbs-akv-handoff}-coverage-20260925-01.service`
  units; only completed passing replays with independent audits count.
  `app_qbs_control_smoke` has since completed PASS with its own independent
  one-case merge audit. A new, non-overwriting 13-case merge at
  `out/integrated-coverage-pass13-qbs-control-20260925-01/` independently
  audits PASS with zero issues. Its DUT-hierarchy hit points are 19,799/38,601
  versus 18,123/38,601 for the 12-case merge; QBS compute, read and block
  adapter coverage all increase. The missed-point review still reports
  `REVIEW_REQUIRED` (13,585 missed of 23,436 source-filtered points). The AKV
  and QBS/AKV handoff replays remain pending and are not in this merge.
  `out/integrated-signoff-snapshot-20260925-01/` contains a reproducible
  machine-readable and Markdown signoff snapshot. Its new
  `coverage_incremental_integrity` gate passes for the 13-case merge without
  replacing the original full-coverage or uncovered-risk gates. Overall
  status remains FAIL: `linux_boot` and `store_b_error` fail; full coverage,
  closure and the final-image real-data pair audit remain pending. The
  report's nine unit tests pass, including rejection of a substituted QBS
  coverage case or mismatched simulator image. The rechecked snapshot is at
  `out/integrated-signoff-snapshot-20260925-02/` and still reports overall
  FAIL while its incremental-coverage integrity gate remains PASS.
  `app_qbs_akv_handoff_smoke` has also completed a PASS replay and independent
  single-case audit on the same instrumented image. A non-overwriting 14-case
  merge at `out/integrated-coverage-pass14-qbs-handoff-20260925-01/` passes
  independent integrity audit: DUT-hierarchy hit points rise from 19,799 to
  20,388/38,601; source-filtered missed points fall from 13,585 to 13,066
  of 23,436. Its review still requires disposition. AKV context replay is
  pending and is not included. The automated snapshot above remains the
  earlier 13-case snapshot until the current coverage set is settled.
  A separate line/expression/toggle-instrumented Verilator image is building
  under `ara-dsa-integrated-verilator-toggle-build-20260925-01.service` at
  `out/integrated-verilator-toggle-20260925-01/`. Its 509-input source
  manifest is frozen; comparison against the line/expression image found
  only the two build directories' generated filelists and signatures differ.
  This is not yet a passing toggle run, nor does Verilator expression coverage
  establish VCS-style condition or FSM-transition coverage.
- The single-hart fast Linux SoC run under
  `/home/wangwy/openproject/ara_dsa_masked_indexed_fix/verification/out/soc-single-hart-fast-vcs-20260925-01/`
  is a boot-speed experiment on an older RTL package. Matching QEMU boot
  and RVV userspace checks passed, but no RTL userspace marker has yet been
  observed. Even a later PASS there must be repeated or source-equivalence
  justified on the final integrated RTL before complete Linux signoff.
  The separate final-source package at
  `out/integrated-linux-package-20260925-01/` was derived from that sealed
  single-hart package with exactly the final `masku`, `vldu` and `vstu`
  changes. Its derivation and seal check PASS. The final-source SoC VCS image
  at `out/integrated-linux-soc-compile-20260925-01/` compiled successfully
  with a passing technology-model check; its separate full-boot simulation
  completed compilation but its separate boot simulation hit the 7200-second
  wall limit without a userspace marker. Its independent boot audit is FAIL
  for incomplete boot; the timeout alone does not identify an RTL functional
  error. Earlier repeated PCs near `0xffffffff8080f1c8` mapped to
  `__init_single_page`/`memmap_init_range` in the matching kernel `System.map`,
  with continuing commits and DDR traffic. Compilation and kernel progress
  do not count as a complete RTL Linux boot PASS.
  The first six-case `linux-fast-prereq` invocation used `--skip-build` before
  its ELF files existed and therefore recorded six input-missing `ERROR`s,
  not RTL failures. A separate retry builds those six programs against the
  final 2 MiB image and runs them with commit traces at
  `out/integrated-linux-fast-prereq-built-20260925-01/`. All six passed;
  `independent_audit.json` separately rechecked frozen inputs and commit
  traces with 6/6 PASS. This closes the named bare-metal prerequisites only,
  not the Linux boot gate.
  A separate 256 MiB FLATMEM/lean-init Linux bundle at
  `out/integrated-linux-lean-bundle-20260925-01/` uses the previously
  QEMU-checked kernel and the same checked initramfs. Its DTB advertises
  exactly 256 MiB, with matching embedded and external copies. The derived
  SoC package at `out/integrated-linux-lean-candidate-20260925-01/`
  preserves the base package's RTL hashes. The run directory
  `out/integrated-linux-lean-soc-20260925-02/` passed the runner's
  compiled-source/include/defines and image-hash reuse checks against the
  final-source SoC VCS image. Its full-boot attempt reached about 30.35
  million advancing cycles and early kernel initialization but hit the 7,200 s
  wall limit without `/init`; the independent audit is FAIL. No panic or RTL
  assertion was observed in this run, so timeout is not an RTL root cause.
  The original 2 GiB attempt remains untouched. An isolated DTS template at
  `verification/linux/ara_soc_loglevel3.dts.in` differs from the frozen
  256 MiB template only in `loglevel=7` to `loglevel=3`. Both settings pass
  the same lean Image/initramfs RVV userspace contract on QEMU; their console
  logs are 18,280 and 4,593 bytes respectively. The new bundle's Image and
  initramfs hashes match the previous bundle, but its rebuilt OpenSBI ELF is
  not byte-identical. Its derived SoC package again preserves all RTL hashes,
  and `out/integrated-linux-lean-l3-soc-20260925-02/` passed final-source VCS
  image reuse checks. A full l3 RTL boot is running under
  `ara-dsa-integrated-linux-lean-l3-run-20260925-01.service`; it has no boot
  PASS until `/init`, all RVV markers and an independent audit complete.
- AXI store B=`DECERR` has been measured reaching VSTU without an
  architectural fault. This unresolved exception/response-ownership gap
  remains a signoff blocker. The final RTL's VSTU B-channel logic at
  `hardware/src/vlsu/vstu.sv` consumes the response by decrementing
  `pending_b` without examining `axi_b_i.resp`; sequencer response may have
  already been accepted before B completion. A fix must preserve instruction
  and element ownership through B and hold or reconcile the architectural
  response. A new final-image one-element vector-store test to unmapped
  `0xe0000000` independently confirms the architectural failure: the matched
  Spike reference exits successfully, but the RTL issues AW/W/B and reports
  no trap. `out/integrated-store-b-error/independent_audit.json` is 0/1 FAIL;
  normal-path results do not waive this fault case.
  An isolated candidate at
  `/home/wangwy/openproject/ara_dsa_store_fault_fix_20260925/` now retains
  per-burst B ownership and delays a store's upstream completion until its B
  response. Its focused `rvv:vstore_axi_error` VCS self-check passes, as do
  `rvv:vstore_signature`, `rvv:vstore_mask_tail_edges`, and
  `app:qbs_akv_handoff_smoke` on the candidate image. The two normal-store
  cases also pass on the original final image using byte-identical ELFs.
  However, a source-manifest comparison found that the first isolated image
  lacked two CVA6 local fixes (`load_unit.sv`, `sram_cache.sv`) present in the
  official image. Its cycle comparison is invalid for attributing the B fix,
  and its passing ten-seed load/store replay is exploratory rather than a
  source-aligned final regression. Those two dependency files are now
  byte-identical to the official image. The rebuilt source-aligned candidate
  passes three store cases, the QBS/AKV smoke case, and AXPY, each with an
  independent frozen-input audit. However, its simulator configuration has
  QBS disabled, no AXI delay, and a 1 MiB L2, whereas the official image
  enables QBS and AXI delay and uses a 2 MiB L2. The AXPY cycle comparison
  is therefore still invalid. A configuration-matched candidate image is
  now built separately. Its AXI fault, AXPY and QBS/AKV smoke cases pass
  independent frozen-input audits; ten frozen load/store random points also
  pass a strict trace/vector/full-match audit. With a byte-identical AXPY
  ELF and matching simulator configuration, the candidate took 3193 cycles
  versus 2786 on the official image (14.6% slower). The official image also
  contains UVM monitor sources absent from that first candidate. A second
  image compiled those same UVM sources and retained the exact 3193-cycle
  result for the same frozen AXPY ELF; its independent commit-trace audit
  passes. The repeated store PC retires every 98 cycles on the candidate
  versus every 85 cycles on the official image, consistent with waiting for
  each B response before architectural store completion. Thus the 14.6%
  AXPY regression is real in this delayed-AXI verification configuration;
  the fault fix is not yet performance-accepted.
  This candidate is not merged or signed off: multi-burst fault precision,
  source-aligned broader regression, synthesis and the possible throughput
  effect of B-gated store completion still require review. The random-only
  terminal re-auditor cannot consume
  this directed-run output format, so its invocation is not counted as an
  independent directed audit.
  The final-source masked/indexed Verilator coverage collector has completed
  three passing case replays and a passing independent artifact audit at
  `out/integrated-coverage-masked-indexed-20260925-01/`. Its missed points
  remain review items; the global code-coverage merge is still pending. This
  image instruments line and expression coverage, from which the report also
  classifies branch points. It does not collect toggle coverage, and there
  is no separately signed-off FSM-transition or assertion/cover-property
  coverage metric. The three-case DUT-hierarchy audit reports line
  3269/8233, branch 6945/15342 and expression 6410/15026; these are partial
  matrix figures, not final merged coverage or a coverage-closure claim.
  The attempted 35-case corners, six-case traced-directed and five-case
  first-matrix collectors were stopped after each had terminal timeout or
  self-check failures: their all-PASS merge contracts could no longer
  succeed. The passing cases and failed diagnostics remain preserved. A
  separate merge at `out/integrated-coverage-pass13-merged-20260925-01/`
  contains exactly 12 PASS replays from the same Verilator image (the
  directory name overstates the count). Its independent integrity audit
  reports PASS, while the uncovered-point review reports `REVIEW_REQUIRED`.
  DUT-hierarchy line coverage is 3555/8233, branch 7466/15342, and
  expression 7102/15026; a narrower source-path filter reports 8483/23436
  points hit. These scopes must not be mixed. Major missed-point groups
  include `ara_dispatcher.sv`, `operand_queue.sv`, QBS units and `vmfpu.sv`.
  A separate final-image VCS run of short QBS/AKV smoke cases is being used
  to select feasible, previously passing Verilator coverage additions.
  The isolated B-error candidate additionally passes a four-element strided
  store to an unmapped address, checking the first error's architectural
  `mcause`, `mtval` and `vstart`. The corresponding independently compiled
  Spike reference also exits successfully with the same self-check source
  (SHA-256 `81945274f62a4a74ceb2db86ab946ed46fbe1d80b2c30544fa31ce8bf2acf2a7`);
  its ELF SHA-256 is
  `04a9f2d4c978f8c8f444d8b8fa2d9bab5af1360b9f922065a43b3b8a3f0c3c16`.
  A stronger revision of that test also puts a mapped store before an
  unmapped second element in one instruction and checks `vstart=1`; both
  RTL and an independently compiled LLVM/Spike reference pass. The UVM
  write-only audit at the candidate's
  `out/store-b-uvm-fault-20260925-02/write_only_audit.json` passes with
  seven matched AW/B responses and two simultaneously outstanding writes.
  The generic UVM wrapper's initial FAIL on this store-only program was
  solely its unrelated requirement for nonempty AXI read traffic; the
  write-channel contract, event traces and backend VID audit pass without
  that read-traffic requirement.
  The candidate's directed frozen-input/trace auditor reports PASS for the
  four-element fault case and the three store regressions, and its QBS/AKV
  handoff smoke passes artifact audit. Two frozen load/store random cases
  pass strict Spike/RTL/vector full-match audit on the first, dependency-
  mismatched candidate image. The same image's ten-seed extension ran 10/10
  PASS with a 10/10 independent strict audit, but neither is final
  source-aligned evidence. Broader precision and regression gates remain.

## Focused triage, 2026-09-25

- Latest check: the seven previously untouched QBS/AKV paired cases all PASS
  in `out/final-qbs-akv-pending-fulltrace-20260925-01/summary.json` on the
  frozen 16 MiB image. All seven input and run hash manifests recheck, and
  each UVM result has zero issues. The isolated `q3_K/rvv` full-trace rerun
  also reports PASS with no UVM issues and matching input/run hashes.
  `q5_K/rvv` and `q6_K/rvv` full-trace reruns remain
  active; neither is counted until its result and hash manifests are audited.
  The original 22-case plan is terminal FAIL because its 100,000-event trace
  cap truncated three RVV cases. Reconciliation must use matching frozen ELFs
  and simulator, and it must not overwrite the original runs.
- The candidate Verilator coverage simulator has built successfully. Its
  independent passing-case matrices and coverage review are still active.
  Two previously passing random seeds (`load_store` seed 7 and
  `integer_stress` seed 6) are being replayed in parallel on the combined
  two-fix VCS overlay, with separate output directories and Spike comparison.
  These jobs are regression evidence, not a substitute for final-source RTL
  integration and a full rerun.
- The `load_store` seed 7 combined-overlay replay has completed with
  `TERMINAL_MATCH`, vector-write PASS and independent strict audit PASS at
  `out/final-mask-bundle-regress-loadstore-seed7-20260925-01/`. The integer
  seed 6 replay has also completed with the same strict results at
  `out/final-mask-bundle-regress-integer-seed6-20260925-01/`. The frozen
  `load_store` and `integer_stress` ten-seed profiles are now replaying on
  the same combined overlay with two workers per profile and separate outputs
  under `out/final-mask-bundle-{loadstore,integer}-10seed-20260925-01/`.
  The other five frozen ten-seed profiles (`arithmetic`, `fp32`, `fp64`,
  `mixed`, `vtype_churn`) are also replaying on that image, one worker per
  profile. The image's 457-source manifest still checks PASS. None of these
  seven profile runs counts as PASS until it terminates and each output passes
  a separate strict trace/vector/full-match audit.
  The candidate coverage image has a separate
  two-case masked-indexed merge with independent evidence PASS, but it
  predates the bundled-mask and gather overlays; it is not final RTL coverage.
- A separate frozen indexed-store seed 72 probe in
  `MASKED_INDEXED_FAULT_FIX.md` observed AXI B=`DECERR` reaching VSTU without
  an exception. This remains an unresolved store-error contract; it requires
  response-to-instruction/element ownership and ordered exception reporting,
  not a one-bit error latch. No signoff claim includes that case.

- Frozen `load_store` seed 6 still reports `RTL_STALL` on the original image and
  on the input-only atomic-mask overlay. A bounded cycle 1118-1140 handoff
  trace at `out/final-mask-handoff-probe-20260925-01/run/console.log` shows
  MASKU sending owner 2 with lane-valid `0011` at cycle 1124, while VLDu's
  independent lane spill registers simultaneously hold old owner 1 in lane 0
  and new owner 2 in lane 1. Their shared drain removes both generations;
  VLDu later exposes owner 2 with only lane-valid `0001`, leaving the indexed
  element's predicate unavailable. A single bundled mask-word spill in
  `out/final-mask-bundle-replays-20260925-02/` passes both frozen failing
  seeds with strict Spike/vector independent audits and rechecked source/input
  hashes. Five focused load/store, mask and `vstart` directed cases also PASS
  with an independent audit in `out/final-mask-bundle-directed-20260925-02/`.
  This is an isolated overlay, not yet merged source RTL or whole-image signoff.
- The same bundle overlay image replays the frozen real Qwen2.5 QBS+AKV ELF in
  `out/final-mask-bundle-qwen-20260925-01/`: UVM reports PASS with 3,532/3,532
  CVXIF requests/responses and 3,155/3,155 backend allocations/completions.
  Both input and run SHA-256 manifests recheck.
- Frozen `integer_stress` seed 5 reports `RTL_STALL` on the original image.
  The bounded gather trace in
  `out/final-integer-seed5-gather-bound-20260925-01/console.log` shows an
  out-of-range gather index consuming a source operand needed by the following
  in-range index. The isolated MASKU overlay gates source-operand readiness for
  out-of-range gather indices. Seed 5 then passes strict Spike/vector audit in
  `out/final-twofix-frozen-replays-20260925-01/integer_stress/`, and frozen
  `vrgather_edges` plus `vcompress_edges` pass directed recheck in
  `out/final-gather-overlay-regression-20260925-02/`. This patch is still an
  overlay, not the final source RTL.
- The `q3_K` and `q5_K` RVV paired programs self-check, but their original
  UVM and contract evidence is truncated by the 100,000-event trace limit and
  therefore remains FAIL. Only those frozen ELFs are being rerun with 400,000
  events in `out/final-qbs-akv-q3-rvv-fulltrace-20260925-01/` and
  `out/final-qbs-akv-q5-rvv-fulltrace-20260925-01/`; do not count them as PASS
  until full handshake/backend evidence and hashes validate.
- The 22-case QBS/AKV paired campaign, final Linux boot and current-image
  Verilator coverage build remain independent background gates. Previous
  passing images cannot be substituted for the final source image.
- The original paired runner stops dispatching after its first failed case.
  Seven untouched cases were therefore frozen into
  `out/final-qbs-akv-pending-fulltrace-20260925-01/frozen_plan.json` and are
  running independently with three workers and 400,000-event traces. The
  original outputs remain immutable; `verification/qbs/reconcile_fulltrace.py`
  will accept only matching ELF/simulator hashes and passing complete evidence
  before running the original paired auditor on a derived manifest.
- `out/final-rvv-70seed-passing-static-coverage-20260925-01.json` accepts 68
  strictly passing random source programs and rejects the two stalled seeds.
  Its static parser sees all planned SEW, LMUL and memory-mode bins, but only
  `tu/mu` policy: byte-exact random differential tests deliberately normalize
  agnostic policy. This is not DUT code or dynamic execution coverage.
  `rvv:vpolicy_type_matrix` separately PASSes as a directed policy test on the
  candidate image; the final image must retain that evidence.

The table below preserves image-specific historical gates; this dated triage
supersedes any older "current-image" shorthand in those entries.

| Gate | Current status | Frozen evidence and scope | Still required |
| --- | --- | --- | --- |
| Directed RVV and random Spike/RTL | Partial PASS; current-image FP32, FP64, load/store, vtype churn and integer stress ten-seed strict audits PASS | Earlier post-fix ten-seed full-state checkpoint, load/store and FP32 batches each passed 10/10 with independent strict audits. Arithmetic passed 10/10 on the WAW-fixed image (`out/rvv-waw-arithmetic-10seed-20260924-01/independent_audit.json`), and its exact frozen failing seed also passed on the combined WAW/divider image. The older FP64 batch had `fp64_8` RTL_STALL and a correctly failing audit; the combined image now passes 10/10 each for FP64, FP32 and load/store with independent strict audits (`out/rvv-waw-div-fp64-10seed-20260924-01/independent_audit.json`). Current-image vtype churn and integer stress each pass 10/10 in their `verification_audit.json`. The previously timed-out mixed-control seed 49 now passes a frozen-input replay and independent terminal/vector audit at `out/rvv-current-mixed-seed49-frozen-20260924-01/`. Earlier 217-case directed regression had one 300-second `vlsseg` timeout; the same ELF/image passed separately in 488.84 seconds with independent audit. Details and original failures remain below. | Finish the other current-image random profiles and audit each separately. One seed per remaining random profile does not close RVV 1.0; some vector destinations remain unobservable in commit-only checks. |
| Directed RVV reductions | PASS for 18 self-checking cases | The post-VSTU-fix image ran `out/rvv-reductions-vstu-fixed-20260924-01/summary.json` and `verification_audit_directed.json`: 18/18 PASS with commit-trace validation and frozen-input re-audit. The earlier image also PASSed 18/18 at `out/rvv-reductions-built-20260924-01/`. The preceding `out/rvv-reductions-current-20260924-01/` attempt had 16 missing binaries, not RTL failures. | These are program self-checks, not Spike full-state matches; the stronger full-match audit is inapplicable to this suite. Its failed diagnostic output remains in `verification_audit.json`. |
| RVV corner cases | PASS for 34 self-checking cases | The post-VSTU-fix image ran `out/rvv-corners-vstu-fixed-20260924-01/summary.json` and `verification_audit_directed.json`: 34/34 PASS with commit-trace and frozen-input re-audit. The earlier image also PASSed 34/34 at `out/rvv-corners-current-20260924-01/`. | Program self-check and valid trace are not a substitute for Spike full-state comparison. |
| RVV historical failure regression | PASS for 14 self-checking cases | One post-VSTU-fix VCS image ran all 14 cases: `out/rvv-failure-fixed-20260924-01/summary.json` and `verification_audit_directed.json` both report 14/14 PASS with trace and frozen-input re-audit. `vssseg` completed in 49.66 seconds; `vlsseg` needed 483.39 seconds. Three additional store/segment regression cases also PASSed separately in `out/rvv-store-fixed-20260924-01/` and `out/rvv-segment-fixed-20260924-01/`. | Self-checking programs and valid traces do not constitute Spike full-state comparison. Linux/coverage on the fixed image remain to be checked. |
| RVV configuration activity | Observed, not functional signoff | `out/rvv-activity-current-image-18cases-20260924-01.json`: 18 accepted cases, one complete VCS image, 88/88 legal SEW x LMUL x policy activity bins and 7/7 memory-mode bins. Five cases contain vector writeback comparison evidence. | Do not equate retired activity or skipped unknown bytes with architectural correctness. |
| CVXIF/UVM protocol | PASS for current six-case matrix, 24/24 planned bins | The combined WAW/divider-fix RTL was compiled into an isolated verification-only image with QBS/AKV-v2 and `verify_axi_delay=1` at `out/rvv-waw-div-uvm-delay-image-20260924-01/`. One simulator image passed RVV, QBS, AKV, read-reset, write-reset and a two-round self-checking AKV column case. `matrix/independent_uvm_coverage_6case.json` rechecked all six frozen inputs/logs/traces with zero evidence errors and closed 24/24 planned bins. `out/signoff-uvm-waw-div-delay-20260924-01/signoff.json` independently reports the `uvm` gate PASS. The full original `akv_portability_smoke` also PASSed on the non-delayed combined RTL image in about 717 CPU seconds; its separate six-case audit reached 23/24 bins, missing only AW backpressure. | This closes the planned UVM protocol bin set for this verification configuration, not RVV functional breadth, the separate real-model pairs, DUT code coverage or Linux boot. |
| QBS/AKV real-model pairs | PASS for 22 program runs, 11 pairs | The corrected 16 MiB QBS+AKV-v2 image under `out/real-ara-uvm-misaligned-qbs-akv-16m-20260924-01/` ran ten QBS/RVV format-and-shape pairs plus one AKV/RVV real-data pair. `out/qbs-akv-pairs-correct-image-20260924-01/independent_reaudit_20260924.json` independently reports PASS, zero issues, matching VCS images, ten QBS pairs and no missing required formats. The formal `out/signoff-qbs-pairs-final-20260924-01/signoff.json` records the `qbs-pairs` gate PASS. The separate combined real-data program at `out/qbs-akv-combined-correct-image-20260924-01/` also PASSed with QBS and AKV-v2 active, 3532/3532 CVXIF requests/responses, 3155/3155 backend allocations/completions and zero UVM errors. Earlier 1 MiB and feature-disabled attempts remain excluded. | This closes the planned representative paired matrix on this image, not arbitrary model/shape coverage or Linux integration. |
| Linux kernel-entry milestone | Prior audited PASS; latest full run observed kernel progress | `out/soc-linux-version-probe-20260923-01/milestone_audit.json` independently rechecked the frozen VCS image and UART `Linux version 6.19.6` marker. The later minimal 256 MiB run reached 32.7 million cycles with increasing commits/DDR traffic and further kernel messages, then hit its 7,200-second wall-clock limit. | A kernel-version marker or partial initialization is not init/userspace completion; the latest timed-out run is not a full-boot PASS. |
| Complete Linux RTL boot | FAIL: no init or userspace marker | An earlier exact-current 256 MiB run reached cycle 111,279,259 before a selected D-cache byte became X and triggered `a_invalid_write_data` (`out/soc-current-waw-div-stvec-linux-reused-20260924-01/failure_audit.json`). The newer minimal run under `out/soc-minimal-linux-compile-20260924-01/` timed out at 32.7 million cycles without a first RTL assertion; its independent `failure_audit.json` reports FAIL. Both runs predate the latest VLDu fix. | Resolve or rule out the cache/refill X with bounded evidence, and complete a hash-frozen final-image boot with RVV and fallback userspace markers. Do not count timeout or kernel-entry markers as full boot. |

The minimal 256 MiB Linux package under
`out/soc-minimal-linux-compile-20260924-01/` uses an Image whose SHA-256
matches the retained build's Image (`8eabad2e5aca714699268d3e7106885da14144aabbe8ad279cce4de946032f6d`).
It reached 32.7 million SoC cycles and printed additional kernel initialization
messages, with increasing commits and DDR transactions. It then exhausted its
7,200-second wall-clock budget; `summary.json` records `simulation.timeout=true`
and `LINUX_BOOT_FAILED`, not a first RTL assertion or architectural mismatch.
The independent `failure_audit.json` correctly reports FAIL because init,
RVV userspace and final SoC markers were absent. This run establishes kernel
entry and progress only, and its RTL predates the latest VLDu fault-order fix.

The exact-current Linux run's first selected-byte X occurred at cycle
111,279,259, PC `0xffffffff80a88c06` (`__pi_memcpy`), after the 1.548772-second
TCP table marker. The cache hit returned `xxxxxxxx00000001`; the refill data
also had unknown bytes. The existing `req_addr=0x6e4` diagnostic is **not a
reliable physical address**: CVA6 supplies the virtual cache index at
`data_gnt`, but the translated tag becomes valid in a later `tag_valid` cycle.
The testbench probe now records those pieces at their proper handshakes;
the first compile passed, but review found that a misplaced `begin`/`end`
cleared the probe's pending-tag flag on every clock edge. This testbench-only
error is corrected. An initial relaunch used system Python and stopped before
compilation because `pyelftools` was absent. The corrected probe compiled in
the project's SoC virtual environment at
`out/soc-cache-tag-probe-compile-20260924-04/` (`COMPILED_NOT_RUN`, VCS exit 0,
simulator SHA-256 `0ac6d1496ffd6e15bbe8d8235b3268c4ddd84cc891bc6778521d34d83f9e537a`).
It has not yet reproduced the old Linux failure. The DDR model's
default `UninitializedData="undefined"` returns X on never-written bytes,
so an uninitialized refill is a concrete alternative to an RTL cache fault,
not yet an established root cause. Do not relax the selected-byte-X signoff
condition on this evidence alone.

| Gate | Current status | Frozen evidence and scope | Still required |
| --- | --- | --- | --- |
| Verilator DUT code coverage | Six passing RVV/QBS/AKV/ALU/FP32/division cases merged; coverage review open | The exit-latch-corrected image has a 496-input source manifest. The original three-case `out/verilator-coverage-signoff-matrix-20260924-01/merged/` baseline had 8,875/23,344 DUT-source points (38.0%). The independently hash-checked ALU, FP32 and division cases passed on the same simulator SHA. `out/verilator-coverage-sixcase-20260924-01/merged/` has 9,883/23,344 points (42.3%). Its independent audit reports six cases, PASS and zero issues; the formal integrity-only gate also PASSes. `review.json` lists 13,461 missed points. | Expand passing stimuli, inspect missed points and justify true exclusions; this is not code-coverage closure. The image predates the indexed-exception `vstart` RTL fix and must be rebuilt for final-image coverage. The separate AKV column stimulus under `out/verilator-coverage-akv-column-20260924-02/` exhausted its 3,600-second timeout before completing 40,000 cycles, so its result is FAIL and is excluded from the merge. |

The exit-latch Verilator rebuild completed and captured a 496-input source
manifest at `out/verilator-coverage-exit-latch-20260924-01/source_manifest.json`.
The gated finalizer rechecked the manifest and ELF RAM fit before starting its
RVV run. That case now reports PASS with simulator and coverage reporter exit
codes both zero, program self-check PASS, and a recorded `coverage.dat` SHA-256
of `7ab5cbcf00756de5e256f27881e2ca4071c0395cea7d2c076bc1ca7ece234d5f`.
Independent rehashing matches the frozen simulator and ELF hashes in its
`result.json`. Its unmerged DUT-hierarchy raw count is 16,424/38,477 points,
including 3,276/8,223 line, 6,925/15,308 branch and 6,223/14,946 expression
points. These are one-case activity counts, not final DUT coverage closure.
All 494 repository source/configuration inputs listed in that manifest
have modification times preceding the rebuild's 08:18:09 local start; the
build output and manifest were written at 10:58:50. This supports source
stability during compilation; the subsequent QBS/AKV runs, same-image merge
and independent integrity audit all passed. Do not attribute later RTL
changes to this frozen Verilator image.

Preliminary coverage only: the old RVV short case's `coverage.dat` (SHA-256
`43e1db84f98892704847bd843ac4e1a058727b590ebab66ae5abc38c05f4b4c9`)
has 6,914 hit points out of 23,344 points in the requested DUT/source scope.
Its `qbs_engine.sv` and `akv_engine.sv` counts are only 64/435 and 46/433,
respectively, as expected from an RVV-only stimulus. This file came from a
testbench with nonzero process exit and is **diagnostic**, excluded from the
passing-case merge and any coverage signoff. The corrected three-case matrix
is the current coverage baseline; its missed-point review remains open.

The long `rv64uv-ara-vadd` directed case passed VCS/UVM on the same image used
for the three-case coverage source matrix: `out/uvm-vadd-coverage-source-20260924-01/`
has 388/388 CVXIF requests/responses, zero protocol errors, and rechecked
frozen input/output hashes. It retires at about 65,540 cycles and is too long
for efficient instrumented coverage. A separate short self-checking ALU
stimulus was built with GNU RISC-V GCC. The first VCS attempt using
`out/rvv-alu-coverage-smoke-build-20260924-03/` was stopped after its trace
showed infinite recursion in the test runtime's `memset`: GCC had converted
the function's byte loop to a call to itself. This is an invalid test ELF,
not an RTL failure. Disabling that rewrite removed the recursion, but the
second GNU/HTIF runtime ELF then waited for a `fromhost` response that this
Ara testbench does not provide. Both attempts were stopped and excluded from
coverage evidence. The stimulus now uses the repository's standard `apps`
LLVM/Ara runtime and linker, the same path as the passing long `vadd`. The
resulting short ELF is `apps/bin/rv64uv-ara-vadd_coverage_smoke` (SHA-256
`d5e5e6da2861db36f807352e62159e29dd99a7db821d3752bb32668c2ef6e2eb`);
its disassembly contains unmasked and masked `vadd`, and its 1 MiB fit check
passed. Its independent VCS run under `out/uvm-alu-smoke-20260924-03/` is
PASS on the same VCS simulator SHA as the three-case source matrix: 42/42
CVXIF requests/responses, zero exceptions or protocol errors, and frozen
input/output hash checks PASS. Its instrumented Verilator run under
`out/verilator-coverage-alu-smoke-20260924-01/` also passed: simulator and
coverage reporter returned zero, self-check passed, and the ELF, simulator,
and `coverage.dat` SHA-256 values independently match `result.json`. This
case is included in the four-case merge above.

The four-case DUT-source review remains uneven. Relative to the three-case
baseline, `simd_alu.sv` rose from 4/867 to 105/867, `masku.sv` from 147/692
to 238/692, `ara_dispatcher.sv` from 689/2,613 to 754/2,613, and
`operand_queue.sv` from 319/1,664 to 378/1,664. `vmfpu.sv` stayed at
422/1,267. Other measured increases are `valu.sv` +93, `sldu.sv` +61,
`lane_sequencer.sv` +51 and `operand_requester.sv` +34. This confirms that
the short stimulus reached arithmetic, mask and operand-delivery paths; it
does not establish broad instruction or branch coverage. The short ALU case
does not close the dispatcher, operand-queue, MFPU or MASKU gaps. Review
passing arithmetic, masked, memory, and real-model stimuli separately before
selecting further coverage cases; retain the per-source missed-point list in
the merged
`review.json`.

The formal `run_signoff.py --stage coverage-integrity` gate also passed with
`--coverage-minimum-cases 4` at
`out/signoff-coverage-fourcase-20260924-01/signoff.json`. This rechecks the
frozen four-case collection and merge; it is deliberately not a functional
or coverage-closure signoff, and the uncovered-point review remains open.

A short FP32 vector add/multiply/fused-MAC case now targets the unchanged
MFPU gap. `apps/bin/rv64uv-ara-vfpu_coverage_smoke` was built with the project
LLVM/Ara runtime; its disassembly contains `vfadd.vv`, `vfmul.vv` and
`vfmacc.vv`, and its 1 MiB ELF fit check passed. The frozen VCS/UVM run under
`out/rvv-waw-div-uvm-delay-image-20260924-01/tests/rv64uv-ara-vfpu_coverage_smoke/`
reports self-check PASS, 29/29 CVXIF requests/responses, 9/9 backend
allocations/completions and zero exceptions or protocol errors. The copied
ELF SHA-256 is
`84963676e289892fc2afceb14d7559fee6580e2f49a6c6f6e043fcd3a1ddb280`,
matching the build. Its independent Verilator run at
`out/verilator-coverage-vfpu-smoke-20260924-01/` reports PASS, with simulator
and coverage reporter return codes zero and the self-check marker present.
Independent SHA-256 checks of the frozen simulator, ELF, log, raw coverage and
LCOV report match `result.json`. The five-case merge adds 119 DUT-source hit
points relative to the four-case merge; `vmfpu.sv` rises from 422/1,267 to
500/1,267, while `simd_alu.sv` remains 105/867. The five-case integrity audit
and formal `coverage-integrity` gate PASS, but the 13,748 uncovered points
still require review. A
direct Spike launch is not differential evidence for this ELF: the Ara test
runtime omits Spike's `tohost/fromhost` symbols, so the attempted launch was
stopped without treating it as a functional pass or RTL failure.

The five-case uncovered-point review is source scoped, not a claim that all
misses are reachable. The largest Ara-source gaps are `ara_dispatcher.sv`
1,849 missed points, `operand_queue.sv` 1,281, `vmfpu.sv` 767,
`simd_alu.sv` 762 and `masku.sv` 454. QBS block adaptation still has 430
misses and AKV engine 194. The FP32 stimulus specifically exercised part of
MFPU; it did not close the control, integer arithmetic or quantized-format
branches. Each proposed exclusion or additional stimulus must be checked
against the source and verification plan before changing the denominator.
An additional `vdiv_vstart_edges` ELF, already PASS in the combined-image VCS
directed regression (last traced cycle 14,598), passed the 1 MiB coverage
RAM-fit check. Its frozen copy has SHA-256
`1d8f7c7acc703009106c9edbb8349e5b2ceeefb0f392d852cbb917df80f9dca3`.
The independent Verilator coverage run under
`out/verilator-coverage-vdiv-20260924-01/` passed with a 20,000-cycle bound.
Its self-check, simulator, reporter and frozen input/output hashes passed
the six-case merge's independent audit. The merge at
`out/verilator-coverage-sixcase-20260924-01/merged/` has 9,883/23,344
source-scoped DUT points hit (42.3%), 13,461 missed. Its six-case integrity
audit and formal `coverage-integrity` gate both PASS; `review.json` retains
the uncovered-point list. This is collection integrity, not coverage closure.
The coverage image predates the indexed-exception `vstart` RTL correction;
the final-image coverage merge must be rebuilt after the masked-indexed fix.
An independent instrumented build for the current VLDu-fix RTL was started
under `out/verilator-coverage-current-fix-20260924-01/build/`; its 496-file
source inventory is frozen in the adjacent `source_manifest.json`. The
parameterized seven-case replay manifest is
`verification/coverage/passed_matrix_20260924.json`, consumed by
`run_passed_matrix.py`. All seven frozen source ELFs and their prior passing
coverage artifacts passed input-hash preflight, but no new-image case or
coverage percentage is claimed until that build and replay complete. A
one-shot background continuation now checks build success before replaying
the seven frozen cases; a failed case records `case_replay.json` with its first
error and is excluded from the merge.
The old seven-case audit was also reviewed by unique source line, with separate
"any instance hit" and "all instances hit" counts so replicated lane logic does
not hide unexercised behavior. This is diagnostic only, not a new coverage
denominator. The largest unique-line gaps are still in the dispatcher,
CVA6 decoder/CSR, VMFPU, SIMD ALU and QBS profile decoder; see
`out/verilator-coverage-sevencase-20260924-01/merged/review_source_lines.json`.
The ten real-model QBS/RVV pairs were independently re-audited as PASS with
zero missing formats. All ten QBS ELFs pass the 1 MiB coverage RAM fit check
and frozen-source hash preflight. An independent background continuation will
run `verification/coverage/real_qbs_matrix_20260924.json` on the same new
instrumented image only if the seven-case matrix passes first. VCS/UVM source
PASS is not counted as Verilator PASS until those new runs complete.
If both matrices pass on the same simulator hash, a final independent job
merges all 17 results under
`out/verilator-coverage-combined-17case-20260924-01/`, re-audits the merged
artifacts and records uncovered points. This is still coverage review, not a
claim that every reachable DUT point has been covered.
The real-model AKV-v2 paired ELF is not included in this 1 MiB Verilator
image: its PT_LOAD range ends at `0x801e8518`, beyond the model RAM end
`0x80100000`. The smaller AKV directed case remains in the first matrix;
real-model AKV functional evidence remains the separate VCS/UVM pair. A future
larger-RAM coverage image or a smaller frozen real-data window is needed before
claiming real-model AKV code coverage.
The same frozen ELF passes the independent 2 MiB RAM-fit preflight in
`out/coverage-real-akv-elf-fit-2mb-20260924-01.json`. The coverage matrix
runner now accepts `--ram-bytes` (default 1 MiB), records the selected value
in provenance, and uses it for ELF preflight. This is only a feasibility
check: a separately compiled 2 MiB instrumented simulator and a passing
AKV replay are still required. The in-progress 1 MiB image is unchanged.
The `vwmul` directed test also passed on the current combined VCS image at
`out/rvv-vwmul-current-20260924-01/`: program self-check PASS, 205/205
CVXIF requests/responses, trace audit PASS, and last traced cycle 36,544.
This is not a Spike full-state comparison. Its ELF passed the 1 MiB coverage
RAM-fit check and the frozen copy's SHA-256 matches the VCS ELF
(`1ab7a8ff0c8a2cd11613e48217cec2a169fd246331a700007444d8a1bf68b985`).
The independent 45,000-cycle Verilator `vwmul` coverage job under
`out/verilator-coverage-vwmul-20260924-01/` finished PASS with its program
self-check and simulator/reporter checks. The seven-case merge under
`out/verilator-coverage-sevencase-20260924-01/merged/` has 10,069/23,344
source-scoped DUT points hit (43.1%) and 13,275 missed. Its independent merge
audit and formal `coverage-integrity` gate PASS. This image predates both the
indexed-exception `vstart` and VLDu early-fault corrections; neither the
seven-case merge nor its 43.1% figure is final-image coverage closure.

Verification-tool unit tests: `out/verification-unit-current-20260924-03/junit.xml`
records 870 tests, 823 passed, 47 skipped, zero failures/errors. Its SHA-256
is `5534756ce247c07d9989eec1ba62338d2e837217b86b086d841e80dcf7242fcf`.
This checks the harness and audit utilities, not RTL functionality or DUT
code-coverage closure.

The `RVV-RANDOM` plan names eight profiles. Their most relevant batch evidence
is not interchangeable across RTL images or checker policies:

| Profile | Recorded batch | Strict/current gap |
| --- | --- | --- |
| `arithmetic` | 10/10 PASS on WAW-fixed image; independent audit | Repeat on final fixed image. |
| `load_store` | 10/10 PASS on combined WAW/divider image; independent audit | Repeat on final fixed image with frozen launch inputs. |
| `integer_stress` | 10/10 PASS on current snapshot; strict audit | Recheck after masked-indexed RTL repair. |
| `fp32` | 10/10 PASS on combined WAW/divider image; independent audit | Repeat on final fixed image with frozen launch inputs. |
| `fp64` | 10/10 PASS on combined WAW/divider image; independent audit | Repeat on final fixed image. |
| `vtype_churn` | 10/10 PASS on current snapshot; strict audit | Recheck after masked-indexed RTL repair. |
| `load_store_slide` | 10/10 runner PASS on current snapshot | Strict audit is 9/10; seed 76 has only a matched prefix and masked-indexed fault. |
| `mixed_control` | 8/10 in the 600-second batch; exact seeds 42/49 later passed frozen replays | Run a complete ten-seed final-image batch with independent strict audit. |

The table records what is actually proved, not a whole-RVV signoff. In
particular, a runner `PASS` does not override a failed independent audit.

Checkpoint correction (2026-09-24): the ten-seed checkpoint job above was
stopped after seed 70 exposed an instrumentation defect, not an RTL mismatch.
The checkpoint routine read `fcsr` with `mstatus.FS=Off` and could clobber the
`kernel_sp` register used by riscv-dv's trap handler. Seed 70 recursively
trapped; its Spike log reached about 17 million instructions before timeout.
The prior seed-68 30/30 result remains evidence for its observed vector and
memory checks, but **does not establish valid FCSR checks**: its CVA6 trace
records 15 illegal-instruction exceptions inside 15 checkpoints. The rewriter now enables
FS before the first full-state checkpoint and excludes the trap-stack register
from temporary selection. The runner now rejects checkpoint-local exceptions
from both RVFI and CVA6 exception logs. A fresh seed-68 run at
`out/rvv-checkpoint-seed68-fs-ksp-20260924-01/summary.json` PASSed 30/30
checkpoints, `TERMINAL_MATCH`, and vector-commit comparison in 176 RTL seconds;
an independent scan of its frozen RVFI/CVA6 logs found zero checkpoint traps.
This reinstates the seed-68 full-state claim only for the corrected image and
stimulus. A separate seed-70 single-case run at
`out/rvv-checkpoint-seed70-fs-ksp-20260924-01/` PASSed 20/20 checkpoints,
`TERMINAL_MATCH`, vector-commit comparison and a zero-trap independent scan;
its independently generated program is not byte-identical to the old ten-seed
index-2 case. A clean ten-seed batch began in
`out/rvv-checkpoint-10seed-fs-ksp-20260924-01/` with bounded timeouts, then
was stopped with its partial output preserved when the AddrGen fix superseded
its VCS image. Current-image random coverage remains open.

Current-CVA6 SoC package: `out/soc-current-cva6-stvec-20260924-01/` now
contains a sealed package whose CVA6 sources match this worktree, including
`csr_regfile.sv`. Its independent VCS compile under
`out/soc-current-cva6-stvec-compile-20260924-01/summary.json` reports
`COMPILED_NOT_RUN`; this is a compile result, not a Linux milestone.

Random-signature instrumentation review (2026-09-24): a generated
`vsetvl t0,t0,t0` exposed a rewriter limitation when the destination cannot
carry the normalized vtype without changing the AVL. The rewriter now spills a
temporary GPR through riscv-dv's uniquely identified reserved user-stack
register; it never assumes architectural `sp` remains a valid stack because
random code can use `sp` as an operand. It rejects the transformation if that
reserved stack cannot be identified or aliases the operation. The original
failure was reproduced on an isolated copy, and the previously unrewritten
FP32/FP64 generated sources were checked after the correction. Host tests:
557 run, zero failures, 25 skipped. No original generated ELF or RTL was changed by this
instrumentation fix; the affected ten-seed profiles are rerunning with new
frozen outputs.

The older arithmetic profile was not signed off: its full batch had 9/10 PASS,
but `ara_dsa_rvv1_arithmetic_6` first diverged at PC `0x80002298`,
`vfmv.f.s fs3,v15`, with Spike `0xffffffff3d82f929` versus Ara
`0xffffffff3d82f925`. The frozen one-case replay with accepted-VRF comparison
is under `out/rvv-arithmetic-case6-vrf-replay-ready-20260924-01/`. In that
replay the preceding `vfredosum.vs v0,v20,v19` at PC `0x80002240` writes
`0xc27d06da` on Ara versus `0xc27d06d6` on Spike. The later masked
`vmflt.vv` carries this two-bit difference into `v15` and then the scalar
readback. The most recent `v19` low-256-bit write matches Spike, and the
`v20` lane writes at its most recent update agree with the corresponding
deshuffled Spike bytes. A follow-up reconstruction compared all 49 active
FP32 source elements of the reduction and found seven differing bytes in
`v21`, written by the earlier `vmulhsu.vv` at PC `0x800021a2`. A raw VRF
writeback scan then located the first such difference at `vsra.vi v12,v28,6`
at PC `0x80002136`, whose lane-0 tail used stale source bytes. The frozen
`ARA_DEBUG_VSRA_TAIL` replay under `out/rvv-case6-vsra-probe-r2-20260924-01/`
shows the ALU shifted its supplied source correctly. Chronological accepted
VRF writes reveal the cause: younger `viota.m v28,v0,v0.t` (sequence 1002)
wrote v29 address 116 on lane 0 at cycle 39113 (`ff8c948498889080`), but
older `vdiv.vv v28,v12,v12` (sequence 1001) overwrote that same word at
cycle 39116 (`000101ff010101ff`). The other lanes received the old write
before `viota` at cycles 39110-39112. A reconstruction sorted by architectural
sequence had incorrectly made all 153 `vsra` source bytes appear to match;
physical write order proves a WAW ordering violation across execution units.
The original replay's vector comparison was only a prefix/partially
unobservable result. A narrow sequencer fix now requires older WAW completion
before `VIOTA/VID` can consume operands. The exact frozen seed 107 ELF replayed
on the rebuilt image under `out/rvv-waw-case6-replay-20260924-01/`: 4550
architectural instructions and terminal state match Spike, and accepted VRF
writeback comparison reports PASS (871 vector requests remain unobservable by
this non-intrusive checker). Separate `viota`, `vdivu`, and `vfredmax_boundary`
directed cases and their independent trace audit passed 3/3 under
`out/rvv-waw-directed-regression-20260924-01/`. The full arithmetic ten-seed
rerun on this WAW-fixed image now has 10/10 PASS and an independent strict
trace/vector/stimulus-coverage/full-match/terminal audit at
`out/rvv-waw-arithmetic-10seed-20260924-01/independent_audit.json`. The
combined WAW/divider image separately replayed the exact frozen seed 107 ELF
with PASS under `out/rvv-waw-div-arithmetic-6-replay-20260924-01/`. These
results close the observed arithmetic first failure, not the entire RVV space.

The earlier FP64 profile was not signed off: `ara_dsa_rvv1_fp64_8` stopped after
1,820 matched architectural instructions at PC `0x80001b5e` (`vmorn.mm`).
The next Spike instruction is `vmsgt.vi` at PC `0x80001b62`; Ara recorded
its architecture start but no CVXIF request and then hit the one-million-cycle
commit watchdog. The final trace retains four backend uops in flight:
`vmv.v.v`, `vmand.mm`, `vdivu.vv`, and `vfmsac.vv`. This is a progress stall,
not a demonstrated numerical mismatch. A same-ELF divider probe under
`out/rvv-fp64-div-probe-20260924-01/` shows lane 1/2 `simd_div` stuck with
issue state `WAIT_DONE` and commit state `COMMIT_READY`, while the underlying
serial divider is idle and has no output valid. The bounded transition trace
under `out/rvv-fp64-div-cycle-probe-20260924-01/` shows why: when the result
queue is full, `COMMIT_DONE` holds a valid unaccepted word, but `WAIT_DONE`
returns to `ISSUE_IDLE` on `valid_o` alone. The next word can be accepted
before the previous word retires, and its commit element count underflows from
zero to seven while only one divider input was issued. `simd_div` now leaves
`WAIT_DONE` only on `valid_o && ready_i`. The exact frozen seed 409 ELF then
completed on the rebuilt combined image under
`out/rvv-waw-div-fp64-8-replay-20260924-01/`: 5587 committed instructions
and terminal state match Spike, and accepted VRF writeback comparison reports
PASS (2607 vector requests are unobservable by this checker). `vdivu`, `vdiv`,
`vdiv_vstart_edges`, and `viota` directed cases plus independent trace audit
passed 4/4 under `out/rvv-waw-div-directed-regression-20260924-01/`. The
FP64 ten-seed vector-signature rerun on the combined image now passes 10/10,
with independent strict audit at
`out/rvv-waw-div-fp64-10seed-20260924-01/independent_audit.json`. This closes
the observed FP64 first failure for the ten tested seeds; other RVV profiles
still require current-image regression before whole-design signoff.
The current-image FP32 and load/store ten-seed strict-signature batches each
completed 10/10 PASS under `out/rvv-waw-div-{fp32,load-store}-10seed-20260924-01/`.
Each independent `verification_audit.json` reports 10/10 full
architectural/vector matches and stimulus coverage present. These batches
predate the random runner's private-ELF/VCS-image/Spike hash snapshot, so
their checker policy did not rehash those inputs. Their functional comparison
is valid for the recorded traces, but exact input-image provenance remains
weaker than the final signoff requirement. Future runs copy each ELF into its
case directory, hash the complete VCS image and Spike at launch, and recheck
all three after execution. These two profiles do not close the remaining
random profiles or whole-RVV functional signoff.

The combined WAW/divider image also completed all 14 historical failure
programs at `out/rvv-waw-div-failure-14-20260924-01/`. Their
`verification_audit_functional.json` reports 14/14 PASS with frozen-input
checks. These self-checking programs do not contain full Spike/vector-state
comparisons: `verification_audit.json` intentionally fails a stronger
`--require-full-match` policy for all 14. Count only the functional evidence,
not a strict architecture-state signoff or an RTL mismatch.

The current-image `load_store_slide` batch originally reported 9/10 PASS:
seed 71 diverged at PC `0x80003712` after `vstart=5`, where its selected
unpatched Spike trapped on `vwadd.vv` but Ara executed it. The archived Spike
binary has `VU.vstart_alu=0`; the project reference patch sets this to 1 for
restartable vector ALU instructions. Reusing the exact frozen ELF and Ara
trace with the patched Spike produced `TERMINAL_MATCH` for 7263 commits and
vector writeback `PASS`. The independent one-case output and strict audit are
at `out/load-store-slide-seed71-recompare-v2-20260924-01/`. The original
9/10 result is preserved. A patched-Spike-only diagnostic recomparison at
`out/load-store-slide-patched-spike-10seed-20260924-01/` reports 10/10 PASS.
It began before per-reference-log hashes were added. The independent
ten-seed recomparison at
`out/load-store-slide-patched-signoff-10seed-20260924-01/` now has all ten
`TERMINAL_MATCH` results and a 10/10 strict independent audit in
`verification_audit.json`; neither run changes the original VCS traces.
Because the original random run predates launch-time VCS-image/ELF snapshots,
this recomparison closes the reference mismatch but not final run provenance.
A new one-seed current-image VCS run using the patched Spike and frozen-input
runner passed full-match and stimulus-coverage audit at
`out/rvv-snapshot-patched-seed71-20260924-01/verification_audit.json`.
The corresponding ten-seed current-image run finished in the independent
`out/rvv-current-slide-snapshot-10seed-20260924-01/` directory. Its run
summary reports 10/10 PASS, but the independent strict
`verification_audit.json` passes only 9/10: seed 76 has `PREFIX` architecture
and vector comparisons after an unobservable vector-to-scalar source, with no
terminal match. The batch omitted `--defined-scalar-sources`, and its original
PASS label must not be treated as full-state signoff. A separately generated
one-seed test with defined scalar sources at
`out/rvv-current-slide-seed76-defined-source-20260924-01/` is not a replay
of the original index-5 ELF. It reached a different vector load at PC
`0x800005c2`; Ara reported load-address-misaligned at `0x8000ae06` while
Spike continued. This is a separate RTL issue, not evidence about the
original prefix case: the instruction is masked `vloxei16.v` with `vstart=1`
and `vl=2`. Its only candidate element is index 1; the frozen Spike state
has `v0[1]=0` and `v23[1]=0x13ee`, exactly explaining the rejected address
`base + 0x13ee = 0x8000ae06`. AddrGen checks indexed EEW alignment without
per-element mask input (`addrgen.sv` has an explicit TODO for masked-element
exceptions); VLDUs receive the mask later for result byte enables. No RTL
change has been made for this issue yet. The focused
`rvv:vmasked_indexed_alignment` test reproduces it on the current VCS image
at `out/rvv-masked-indexed-alignment-prefx-20260924-01/`: the masked load
records one unexpected trap and the program fails, while its aligned active
control reaches the result check without another trap. The current bare-metal
ELF has no HTIF `tohost` symbol, so a direct Spike launch of this new test
cannot serve as terminal reference evidence; the frozen random-test Spike
trace above supplies the discriminating mask/address observation. A separately
compiled bound probe reproduced the directed fault with frozen ELF and full
VCS image hashes at `out/rvv-masked-indexed-probe-run-20260924-02/`:
AddrGen decided the fault in probe cycle 460, one cycle before the mask
reached VLDu input and two cycles before its spill register held it. The
aligned active control likewise sent AR before its mask arrived. This rules
out a combinational mask tap at the existing address-decision cycle; RTL
repair and same-image regression remain open. The separately frozen
indexed-store probe at
`out/rvv-masked-indexed-store-probe-run-20260924-01/` also failed: a
masked-off misaligned store raised an exception at probe cycle 466, after
which AddrGen held the same index without a descriptor or AW/W transaction.
The bounded diagnostic timed out, so its later active-store checks were not
reached. This is a second failing path, not store signoff. The strict random
runner now labels such a prefix `INCOMPLETE_COMPARISON` instead of PASS. The
`rvv-masked-indexed` suite now selects both directed load/store cases, and
`rvv-fast-integrity` also includes them. The updated store ELF compiles as
`apps/bin/rv64uv-ara-vmasked_indexed_store_alignment` (SHA-256
`7338364e8a15ef3549c3f9dd4ecb45448ad84fea92070d5ef67f3af4e652771d`);
its added all-inactive `vstart=0` check also failed on a frozen current VCS
image at `out/rvv-masked-indexed-store-vstart0-current-20260924-01/`:
the store at PC `0x800001aa` raised Store Address Misaligned with
`tval=0x80001306`, and the 120-second diagnostic did not complete. Its later
cases remain untested. A separate bound-probe image and 25-second run at
`out/rvv-masked-indexed-store-id-probe-20260924-01/` showed AddrGen issuing AW
for the first all-inactive element at cycle 473, before VSTu's all-zero mask
input became valid at cycle 475; AddrGen raised the second element's exception
in that same cycle. Both units had instruction ID 0. Thus a correction must
remove the masked memory transaction as well as the false exception. The matching
load probe at `out/rvv-masked-indexed-load-id-probe-20260924-01/`
also saw AR at cycle 459 before mask arrival and a false exception at cycle
461 with an all-zero VLDu mask input; its updated directed test ended FAIL
(`tohost=3`).

A separate indexed-exception `vstart` bug was reproduced and narrowly fixed:
`addrgen.sv` omitted the original `vstart` and shifted the remaining length
by the wrong amount. The frozen unmasked indexed-store test
`rvv:vindexed_fault_vstart` recorded `vstart=2` and `0` before the fix,
where both traps should report `1`. The corrected expression follows the
existing MMU-exception element-count formula. On an isolated new VCS/UVM
image, the same ELF reports `1` for both traps and passes the independent
trace audit at `out/rvv-indexed-fault-vstart-after-20260924-01/`.
`rvv:vindexed_vstart_edges` and `rvv:vunit_vstart_edges` also pass independent
trace audits on that image. Frozen QBS and AKV representative programs pass
their UVM self-checks on the same image. This correction does not address
the masked-off indexed memory transaction and exception fault above.

An expanded indexed-load/store exception test exposed a second precise-fault
ordering bug: an early indexed-load misalignment started VLDu's exception
drain while an older active AR descriptor was still waiting for its R beat.
The first load trapped with `vstart=1` but failed to commit element 0; a
later load saw the orphaned response. Cycle evidence is frozen at
`out/rvv-indexed-load-fault-order-probe-20260924-01/`. VLDu now latches the
early fault and starts exception cleanup only after older descriptors and
responses have drained. On the new isolated image
`out/rvv-indexed-load-fault-fix-image-20260924-01/`, the four-scenario
indexed load/store test PASSes with independent trace audit at
`out/rvv-indexed-fault-load-store-fixed-20260924-01/`. Ordinary indexed and
unit-stride `vstart` regressions also PASS independent audits, and the frozen
QBS and AKV representatives PASS UVM checks on the same image. The masked
indexed load/store issue remains open and is not covered by this correction.
The expanded six-scenario version additionally checks element-0 load and
store faults with no older AR/R; it PASSes independent trace audit at
`out/rvv-indexed-fault-sixscenario-fixed-20260924-01/` on the same fixed image.
The seven-scenario ELF adds two valid indexed load elements before a third
element faults; its frozen input SHA-256 is
`fb131ae7741ef3757b6eff8ea011c98539c643277d72ccebdd2b7b8af943b1ad`.
It PASSes the program and independent trace audit at
`out/rvv-indexed-fault-seven-scenario-20260924-01/`, checking both earlier
results and `vstart=2`. This does not resolve masked indexed accesses.

The current-image `vtype_churn` ten-seed snapshot run under
`out/rvv-current-vtype_churn-snapshot-10seed-20260924-01/` completed 10/10
PASS with independent full-match and stimulus-coverage audit in
`verification_audit.json`. The current-image `integer_stress` snapshot under
`out/rvv-current-integer_stress-snapshot-10seed-20260924-01/` also completed
10/10 PASS with independent strict `verification_audit.json` and zero errors.
The earlier `mixed_control` run reported 8/10 PASS and two 600-second
`RTL_TIMEOUT` results (seeds 42 and 49), with no architectural prefix
mismatch before timeout. An older, different seed-42 ELF from the same profile
needed about 2227 seconds to finish. The timed-out seed-42 Spike trace has
41446 committed rows versus 10089 matched RTL instructions at 600 seconds,
giving a rough full-run estimate of 2465 seconds at the observed rate. The
first diagnostic attempt was stopped early because its 2400-second limit was
too close to that estimate; its partial output remains under
`out/rvv-current-mixed-seed42-diagnostic-20260924-01/`. The exact original
seed-42 ELF completed its diagnostic replay in
`out/rvv-current-mixed-seed42-diagnostic-20260924-02/` with a 3300-second
wall limit and unchanged one-million-cycle watchdog: `summary.json` reports
PASS and `TERMINAL_MATCH` after 2152.048 seconds, with 36441 matched
instructions and 17262 vector destination checks. Thus the earlier 600-second
timeout was a run-budget limit for this exact ELF, not a persistent stall.
This replay is diagnostic, not
frozen-input signoff; its source ELF SHA-256 is
`4b6565bb4dd3f30c463818492051ab367255aca57379b82552f34f0e4b920939`.
A frozen-input replay of this exact seed-42 ELF at
`out/rvv-current-mixed-seed42-frozen-20260924-01/` has completed with primary
`PASS`/`TERMINAL_MATCH` and 36441 matched instructions. Its separate
`independent_terminal_reaudit.json` now reports `PASS` with no issues:
terminal `TERMINAL_MATCH`, complete vector comparison `PASS`, valid trace,
and frozen input and simulator-image hashes. This case is independently
signed off; it does not cover the separate masked-indexed failure.
The original seed-49 ELF had 9150 matched RTL instructions out of 16447
Spike instructions at the 600-second cutoff, also with no prefix mismatch.
The first seed-49 diagnostic at
`out/rvv-current-mixed-seed49-diagnostic-20260924-01/` accidentally used
the riscv-dv generator `vcs_simv`, not the Ara RTL image. It exited at time
zero with `UVM_FATAL [NOCOMP]` and produced no commit trace; this is a setup
error, not an RTL failure. A fresh replay with the Ara image used by the
successful seed-42 diagnostic ran at
`out/rvv-current-mixed-seed49-diagnostic-20260924-02/`, with the original
ELF, a 2400-second wall limit and unchanged one-million-cycle watchdog.
It completed PASS in 605.030 seconds with `TERMINAL_MATCH`, 11447 matched
architectural instructions and vector comparison PASS. This diagnostic
result does not count as strict signoff because this replay predates the
new per-case input snapshots; a separately frozen-input audit is required.
An independent terminal re-audit of these preserved diagnostic logs at
`out/rvv-current-mixed-seed49-diagnostic-20260924-02/independent_terminal_reaudit.json`
also passed: 11447 architectural commits, 3524 vector destination requests,
valid retirement trace and ELF-derived exit PC `0x8000070e`. Requiring
frozen inputs correctly rejects the same old case, so this remains
diagnostic evidence rather than frozen-input signoff.
A frozen-input replay of this exact seed-49 ELF completed in 593.551 seconds
at `out/rvv-current-mixed-seed49-frozen-20260924-01/`. Its independent
`independent_terminal_reaudit.json` reports PASS with no issues: 11447
architectural commits at the ELF-derived ecall, 3524 complete vector
destination requests, a valid retirement trace, and hashes for the frozen
ELF, Spike and all 66 VCS executable/library image parts.
The replay tool now classifies `[NOCOMP]` as
`RTL_SETUP_FAIL` for future runs; the original failed artifact is preserved.
It reports a matched architectural `PREFIX` as `INCOMPLETE_PREFIX`
instead of PASS; only full or verified terminal matches can pass replay.
The independent random-result postprocessor applies the same rule, so a
shared architectural/vector prefix cannot be promoted to PASS during
re-analysis of preserved artifacts.
The random runner also labels a non-strict `PREFIX` as `INCOMPLETE_PREFIX`;
strict vector-state runs retain their existing `INCOMPLETE_COMPARISON` status.
Future replay cases also copy each ELF to `tests/<case>/input.elf`, record its
SHA-256 together with the Spike binary and full VCS executable/library image
in `inputs.json`, and reject changed inputs. The completed seed-49
diagnostic was launched before this change and does not gain those snapshots
retroactively.
Direct random, replay and full-campaign commands
now require an explicit `--spike`, and run a small nonzero-`vstart` `vwadd.vv`
probe before the expensive tests. The probe experimentally rejects the old
Spike and accepts the patched one. No RTL change or repeated VCS simulation
was made for this diagnosis.

The overall status remains **INCOMPLETE**: masked indexed load/store directed
tests fail on the current RTL, complete Linux boot has not been demonstrated,
and DUT code-coverage review and closure remain pending despite the audited
six-case collection. The `PASS` labels above
are limited to
the stated frozen case set and checker scope. Original JSON reports retain
input hashes, executable/image identities, commands and first-error details.
The earlier 216-point post-fix `rvv-directed` snapshot completed 216/216 PASS
under `out/rvv-directed-vstu-fixed-20260924-01/`. Its frozen test list predates
the current 219-point catalog: `vector_misaligned_trap` and both masked
indexed load/store cases were absent. It cannot close those gaps.
The `vector_misaligned_trap` ELF (SHA-256
`864f3a4fc4234092a7011fc9d03e8cc73268cc34da4a3a72525afab207c4e1e0`)
failed on the older `out/vssseg-probe-fixed-20260924-01/` VCS image: both
`vle16.v` and `vse16.v` returned illegal instruction (cause 2, `tval=0`)
instead of load/store address misaligned (causes 4/6, fault address). The
same frozen ELF passed its eight exception checks on the current RTL VCS
image (simv SHA-256
`c3a5a890b19cbe22dfa5dba2d840e4da4a38f8a274eb8ffb1ce41ea1a3e70224`)
at `out/rvv-vector-misaligned-current-probe-20260924-01/`. This closes that
directed case on the current image, not the separate masked-indexed cases.
The initial 116-point
`applications` attempt at `out/applications-vstu-fixed-20260924-01/` stopped
before RTL simulation: its runner linked for 1 MiB L2 while the reused VCS
image was built for 4 MiB. The runner now reads and validates the image's
`simulator.conf` when choosing the app linker size. It also freezes every ELF
under the apps build lock before launching any suite workers, preventing a
concurrent build from mixing program versions within one suite; a binary
missing at freeze time cannot join later. The isolated applications rerun
completed with a partial result, detailed below. Neither suite is counted as
a full PASS without a complete independent audit.

The frozen SoC package is not an exact CVA6 worktree snapshot. Its
`csr_regfile.sv` has different STVEC read/write handling. The former
`load_unit.sv` difference was adopted in the current CVA6 source only after
static review and a 15-case sealed-package load contract; source and package
now share SHA-256 `042db6cbcfdba16f6810a49de010eeb52105829e444a348df5fc7ec89f3ac7dd`.
The `sram_cache.sv` missing reset/user port connections were also brought
into byte-for-byte agreement with the compiled SoC package (SHA-256
`877c026fd6fdbc9d32746fea7f015f70719643df2f3536072367cede7fed1a86`).
Even a successful SoC-package Linux boot cannot alone sign off the exact
current CVA6 RTL while the STVEC difference remains.

To remove that last source mismatch without weakening the existing evidence,
`out/soc-current-cva6-stvec-20260924-01/` is a separately sealed package that
overlays only the current `csr_regfile.sv` (SHA-256
`635466f3c536e290b6cdf208c12cef762ed394fbf701e03c89ecf770420d12f4`).
Its 788-entry seal, Ara RTL inventory, and every CVA6 file shared with the
worktree were checked after derivation. An independent VCS compile-only run
under `out/soc-current-cva6-stvec-compile-20260924-01/` now reports
`COMPILED_NOT_RUN`. The first launcher used system Python without `elftools`
and exited before output preparation; the successful retry used
`verification/tools/soc-venv/bin/python`. Compilation does not constitute a
Linux boot result.

The follow-on exact-current package at
`out/soc-current-waw-div-stvec-20260924-01/package` overlays precisely five
Ara sources (`ara_sequencer.sv`, `simd_div.sv`, `valu.sv`, `vmfpu.sv`, and
`addrgen.sv`) onto that sealed CVA6 package. All 788 seal entries verify;
the packaged Ara source tree matches the current worktree apart from the three
documented host-only SoC files, and packaged CVA6 STVEC matches the current
CVA6 source. Its `derivation.json` preserves old/new hashes and the original
pre-integration hash of the specially preserved VMFPU file. The package
compiled successfully under `out/soc-current-waw-div-stvec-compile-20260924-01/`
with `COMPILED_NOT_RUN`. The run directory
`out/soc-current-waw-div-stvec-linux-reused-20260924-01/` reused the complete
VCS image with matching `simv` SHA-256
`832784ea069d025a1e80520a409af0f81ed2e2582a331143bb0aae4e0a7068b8`;
the Linux run ended in `LINUX_EARLY_FAILURE` at cycle 111,279,259 with
`a_invalid_write_data`, not a completed boot. Its first selected-byte-X
diagnostic and unresolved DDR-versus-cache alternatives are recorded above.
The frozen `Image` must be used for PC attribution; the current Buildroot
`vmlinux` has a different image hash. A smaller, independently QEMU-passing
Linux image with the same RVV userspace payload is being staged as a separate
SoC input bundle at `out/linux-minimal-soc-bundle-20260924-01/` to avoid
replaying unrelated driver initialization. Its sealed exact-RTL package is
`out/soc-current-minimal-linux-20260924-01/package`; the derivation reports
`PREPARED_NOT_RUN`, 256 MiB RAM and unchanged RTL (package seal SHA-256
`9d6b177cb454198cedbbdd199fe5ad4e3db5d6bfc5b84971e84d4b8384e06407`).
QEMU PASS and package preparation do not establish RTL Linux boot.
The derived package then compiled with the corrected cache-tag probe at
`out/soc-minimal-linux-compile-20260924-01/` (`COMPILED_NOT_RUN`, VCS exit 0,
simulator SHA-256 `25b72bde0e071bc591040de45a3c6cf3f95a8bad5dcdfeda3decea4e66344e44`).
Its run-only Linux simulation stopped at the 7,200-second wall limit after
32.7 million advancing SoC cycles. It reached kernel initialization without
an RTL assertion, but not `/init`; the independent audit correctly reports
FAIL. This image predates the later VLDu early-fault correction.

To reduce time spent serializing boot diagnostics over the modeled UART, an
isolated otherwise-identical 256 MiB device tree changes only `loglevel=7` to
`loglevel=6`. The `Linux version` notice and userspace markers remain visible.
QEMU with the same minimal kernel/initramfs reached userspace PASS in both
profiles: the frozen l6 console is 6,937 bytes and the l7 control is 15,229
bytes. A separate l6 replay declared all four existing userspace-profile
markers and passed the unmodified Linux-stage integrity/signoff gate at
`out/signoff-linux-minimal-l6-qemu-20260924-02/signoff.json`. This proves a
QEMU boot preflight with frozen payload hashes, not RTL Linux boot. The l6
bundle is sealed at
`out/linux-minimal-l6-bundle-20260924-01/`. A new sealed SoC package at
`out/soc-current-vldu-fix-l6-20260924-01/package` includes the current
`addrgen.sv` and `vldu.sv` fixes. Its independent VCS compile under
`out/soc-current-vldu-fix-l6-compile-20260924-02/` finished as
`COMPILED_NOT_RUN` with simulator SHA-256
`eecd025ca3e043c24ae79aa112472d13eff3c7c37bab44ee85146793ab8d675c`.
The matching run-only RTL Linux simulation is active in that independent
directory with explicit-failure, first-progress, no-progress and 10,800-second
wall limits. A separate background audit job will run `check_soc_linux.py` and
the Linux signoff gate after this simulation terminates, regardless of whether
it passes. No RTL Linux boot claim is made until those results are inspected.

A separate 16 MiB QBS/AKV-v2/UVM image was compiled after the sequencer and
divider fixes under `out/rvv-waw-div-qbs-akv-16m-image-20260924-01/`.
`source_manifest.json` captures 453 VCS inputs and passed an immediate drift
check. The `applications` suite completed against this image under
`out/rvv-waw-div-qbs-akv-applications-20260924-01/`. Its original summary
records 41 PASS, 26 trace-checker FAIL, and 50 300-second TIMEOUT results.
The 26 trace failures were caused by two checker-only classification errors:
QBS/AKV custom-2 (`0x5b`) was not recognized as an offloaded instruction,
and scalar FP16 loads/stores were incorrectly counted as vector memory
operations. After matching the checker to CVA6's first-pass decoder, all 26
saved traces validate. `trace_checker_reaudit.json` independently rechecks
all 67 completed cases' frozen ELF and complete VCS-image hashes, clean
program-success markers, zero simulator exit codes, and trace ordering. It
reports 41 `RECONFIRMED_PASS`, 26 `PASS_AFTER_CHECKER_FIX`, and 50 unchanged
timeouts, without altering the original summary or rerunning VCS. This gives
67 completed functional passes but does not close the 50 timeouts or the full
suite. The frozen real-model
`q4_K` decode RVV/QBS pair under `out/rvv-waw-div-q4K-pair-20260924-01/`
now has two PASS UVM runs, QBS-specific evidence PASS, and independent
`paired_evidence.json` PASS on the same VCS image SHA-256
`707dd8b58a420f7459ba925b82bf69e4ed4336571d5a25e27598ae1ad9ee22f2`.
For K=1536 and 256 output rows, the measured compute windows are 261653 RVV
cycles and 31236 QBS cycles (8.38x for this slice). Both outputs passed their
llama.cpp golden checks but their output checksums are not bitwise equal; this
is not a bit-exact equivalence claim. The applications suite has no full PASS
verdict.

A later source-manifest recheck reports one changed entry out of 453:
`hardware/Makefile`. This entry changed after the VCS image was compiled when
the Verilator incremental-build recipe was updated; the RTL and selected VCS
source-file entries did not change. Keep the strict manifest result as FAIL
for exact whole-file provenance instead of silently refreshing it. The frozen
VCS image and per-case ELF hashes remain independently checkable; any final
source-level waiver must cite this Makefile-only difference explicitly.

Re-audit the Linux milestone without rerunning VCS:

```bash
python3 verification/fpga/check_soc_milestone.py \
  verification/out/soc-linux-version-probe-20260923-01 \
  --report verification/out/soc-linux-version-probe-20260923-01/milestone_audit.json
```

After the full Linux run stops, independently re-audit it before changing the
table:

```bash
python3 verification/fpga/check_soc_linux.py \
  verification/out/soc-linux-full-quiet-cacheprobe-20260924-01 \
  --report verification/out/soc-linux-full-quiet-cacheprobe-20260924-01/boot_audit.json
```

## 2026-09-25: final-image coverage and isolated store-B candidate

The 20 frozen `memory_cross` random cases in four five-seed batches under
`out/integrated-wred-m8-memory{101,201,301,401}-replay-20260925-01/`
all have PASS VCS/Spike results and independent complete vector/full-match
audits. `coverage/run_directed_coverage.py --random-source` now requires that
audit policy, re-audits the source run, and freezes each ELF before replaying
it on one Verilator coverage image. This is a replay capability, not a claim
that those cases already contributed to a final coverage percentage. The
same current VCS image also replays frozen `arithmetic` and `load_store`
ten-seed batches at `out/integrated-wred-m8-arithmetic10-replay-20260925-02/`
and `out/integrated-wred-m8-loadstore10-replay-20260925-01/`. Both report
10/10 PASS; each `independent_audit.json` requires complete trace, vector,
and full-match comparison and reports zero failures. The frozen FP32 batch at
`out/integrated-wred-m8-fp32-10-replay-20260925-01/` also reports 10/10
PASS with the same independent strict audit. The frozen FP64 batch at
`out/integrated-wred-m8-fp64-10-replay-20260925-01/` independently audits
10/10 PASS as well. The frozen `vtype_churn` batch at
`out/integrated-wred-m8-vtype10-replay-20260925-01/` reports 10/10 PASS;
its `independent_audit.json` requires complete trace, vector, and full-match
comparison and reports zero failures. This makes 70 audited multi-seed random
passes across six profiles on the current VCS image.
`out/integrated-wred-m8-qbs-akv-handoff-20260925-02/` independently audits
one QBS/AKV handoff functional smoke PASS on this VCS image; its program
checks custom-operation results and zero traps. That smoke does not claim
Spike full-state equivalence. The
final-source Verilator line/expression image is still building at
`out/integrated-verilator-coverage-20260925-01/`; its 509-file source manifest
currently rechecks PASS. The older 43.1% seven-case figure is not applicable
to this final RTL image. A toggle-only build is active at
`out/integrated-verilator-toggle-20260925-02/`; its captured source manifest
matches the line/expression build on all 482 RTL, dependency, and testbench
source files. The older toggle build under `...toggle-20260925-01/` is stale:
its manifest predates the dispatcher correction and must not be used as final
coverage evidence. Neither toggle executable nor toggle coverage result is
claimed yet. `ara-dsa-final-toggle-stage1-20260925-01.service` is waiting for
the new build before running one audited register-group directed case and one
QBS/AKV handoff smoke. Its merge will review toggle points only in the
dispatcher, sequencer, VLSU control, QBS, and AKV source paths; this scoped
toggle result is separate from the line/expression percentage.
The local Verilator 5.038 toggle-only tool smoke under
`out/verilator-toggle-tool-smoke-20260925-01/` passed its self-check and wrote
raw `t=toggle` points; `verilator_coverage --write-info` produced nonempty
LCOV. This validates the collection format, not Ara RTL toggle coverage.

The isolated AXI store B-response experiment lives in
`../ara_dsa_store_fault_fix_20260925/`. Waiting for the final B response
preserves precise injected-store-fault behavior, but the matched AXPY ELF
takes 3193 cycles versus 2786 cycles on the original image (+14.6%). A
request-early/response-late variant was measured on a third isolated VCS
image: the store request fired at cycle 483 and the fault response at cycle
551. The existing UVM bind asserts same-cycle request/result, so both runs
failed that assertion; AXPY still took 3193 cycles. CVA6's CV-X-IF
documentation and the separate transaction-ID monitors permit a delayed
result, so the bind assumption alone is not proof of a protocol violation.
An isolated checker correction was evaluated without changing the main
verification image. The RTL variant is **not merged**; the current integration
RTL has no store-B precise-error fix. A later candidate still needs an
independently checked multi-burst fault, correct younger-store visibility,
matched AXPY performance, and valid transaction-ID ordering.

The isolated checker image at
`../ara_dsa_store_fault_fix_20260925/verification/out/store-b-delayed-checker-build-20260925-04/`
removed only the incorrect atomic-request assertion; the existing UVM
scoreboard and independent contract monitor still check outstanding IDs.
Both frozen UVM cases now report PASS with zero issues. The faulting store
request fires at cycle 483, the final observed B fires at cycle 549, and its
exception result fires at cycle 551; the program's trap-time younger-store
sentinel check passes. The matched AXPY remains 3193 cycles, so the candidate
still fails the performance acceptance criterion and remains isolated. This
comparison uses the same ELF (SHA-256
`95d17384bb80addb04586b1884dbd0c8084b1cf26134d80c7c5ff6b0247fea3d`),
but the baseline and candidate are not an RTL-only A/B pair: their VCS images
differ, and their architectural trace summaries report 412 versus 410 retired
instructions. The measured 2786-to-3193-cycle change must therefore not be
attributed solely to waiting for AXI B. Candidate `ara_req_blocked_cycles`
increases from 2132 to 2597 (+465), while `total_rvv_store_only_cycles`
remains 1629; this suggests additional front-end/back-end waiting rather than
longer store activity, but does not by itself isolate the cause. A source-matched
baseline or discriminating cycle trace is required before a causal performance
claim or merge decision.

### Source-matched store-B A/B

`../ara_dsa_store_fault_fix_20260925/verification/out/store-b-source-matched-ab-20260925-01/`
now provides that controlled comparison. The two VCS images were compiled
serially from matching 454-file source manifests; all shared source hashes
match, both manifests independently recheck PASS, and `simulator.conf` differs
only in `store_b_ab_baseline=1` versus `0`. Both AXPY runs use the same frozen
ELF SHA-256 shown above, pass the UVM/AXI checks with zero issues, and have
verified `INPUT_SHA256SUMS` and `RUN_SHA256SUMS`. Early store response is 2786
cycles; waiting for the final B response is 3193 cycles (+407, +14.6%). The
number of vector stores and AXI write completions is unchanged (32 and 33).
`ara_req_blocked_cycles` rises from 2132 to 2597 (+465), while
`total_rvv_store_only_cycles` stays at 1629. This supports the hypothesis that
the precise-response wait serializes request progress, rather than lengthening
the stores' own active interval.

On the precise image, the frozen multiburst AXI fault case passes the UVM
checks without protocol errors; the faulting request fires at cycle 483, the
last B at 549, and its CV-X-IF exception response at 551. The source-matched
performance penalty is not acceptable for integration, so this candidate
remains isolated. A future improvement must preserve the late fault response
and younger-store visibility while recovering overlap, then repeat this same
functional and performance gate before merge.

The stall is not confined to a sequencer-ready bit. In the isolated candidate,
`ara_sequencer.sv` holds its single `WAIT` request until the store's final
`vinsn_done`, and `ara_dispatcher.sv` stays in `WAIT_STORE_RESPONSE` until that
response arrives. CVA6's `acc_dispatcher.sv` only forwards requests after its
transaction ID becomes non-speculative at commit. Thus allowing Ara to accept
a later request while the older store is unresolved is not, by itself, a
demonstrated way to recover the measured 407 cycles: the later request may not
yet be available, and any early architectural progress must still preserve
precise fault ordering. This is a static constraint plus the measured A/B
stall signature, not a cycle-by-cycle proof for every AXPY iteration. The next
candidate needs a discriminating trace of CVA6 commit/accelerator request,
Ara store wait, and AXI B timing before any further RTL change.

The frozen source-matched A/B CVXIF logs have now been compared without another
simulation by `../ara_dsa_store_fault_fix_20260925/verification/uvm/analyze_store_b_ab.py`.
Its hash-bound result is
`../ara_dsa_store_fault_fix_20260925/verification/out/store-b-source-matched-ab-20260925-01/cvxif_store_timing.json`.
Both traces contain 32 matching AXPY stores and no unmatched CVXIF requests.
At the CVXIF interface, the baseline store request/response pairs are
same-cycle; the precise candidate's request-to-response intervals are 73-76
cycles each (2399 cycles summed across stores). The response-to-next-request
interval sums are identical at 93 cycles for the 31 stores with a following
request. Comparing corresponding store response cycles, the candidate trails
by 60 cycles at the first store and 465 at the last, with a repeated 13-cycle
increase through most iterations. These observations support a recurring
serialization cost at the store completion boundary; they do not establish
which internal gate contributes each cycle. The next focused probe must sample
CVA6 commit/request eligibility, sequencer and dispatcher wait states, VSTU
pending-B state, and AXI B handshakes on the same cycle axis before changing RTL.

That bounded cycle-level A/B probe has now run in the isolated worktree under
`verification/out/store-b-cycle-probe-ab-20260925-02/`. Both images use the
same frozen AXPY ELF and 444 identical hardware-source hashes; their simulator
configuration differs only in `store_b_ab_baseline`. Both UVM checks and
output SHA-256 inventories pass. Each probe has 801 contiguous sampled cycles
(400-1200), and the task cycles reproduce 2786 versus 3193. The hash-bound
analysis `first_store_probe_analysis.json` is generated by
`verification/uvm/analyze_store_b_probe.py`; its two source CSVs are retained.
For the first store, both images issue WLAST at wall cycle 526 and accept B at
531; VSTU completes at 532. The baseline CVXIF response is already visible
at 473 and the next request is accepted at 476, while the precise candidate
responds at 533 and accepts the next request at 536. In the identical
wall-cycle interval [457, 533), baseline records six CVA6 commit slots and
three CVXIF request handshakes, versus zero and one on the candidate. The
candidate spends 75 of those cycles in sequencer WAIT; its dispatcher spends
76 cycles in state 15 (`WAIT_STORE_RESPONSE`). The B/pending-B activity is the
same on both sides. This directly confirms loss of overlap while waiting for
precise store completion; it does not prove that a one-cycle control tweak can
restore that overlap. CVA6's accelerator dispatcher only forwards committed,
non-speculative requests, and the current CVXIF store-complete signal has no
late precise-exception payload. Returning success before B would restore
early progress but lose the injected B-error trap; deferring the response
retains precision but blocks younger architectural progress. The tested
candidate therefore remains **not merged**. Any performance-neutral precise
solution needs a separately validated speculative/rollback path, a faster
store completion path, or a different precise-error contract; none is assumed
correct from this A/B result alone.

### Coverage-input provenance limitation

The earlier VCS-image `out/integrated-final-qbs-akv-pairs-20260925-01/` directory
contains individual UVM PASS records for the QBS/RVV and AKV/RVV programs,
but its `audit.json` is **FAIL**, with `qbs_pair_count=0`. The independent
paired-data audit cannot find several original `case.json` files, generated
weight files, or the AKV source input. One Q6_K RVV run also required a later
retry, so merely counting directory entries would be misleading. These
individual self-checks alone do not qualify as independently audited real-data
coverage inputs. The current-image handoff smoke remains the bounded stage-1
stimulus; longer paired-program replay is selected only after stage-1 gap review.
The missing capture inputs are available in `../ara_dsa_verification/`, and
the exact historical `run_real_dut_case.sh` hash recorded by the run manifests
is available in `../ara_dsa_masked_indexed_fix/`. A separate rebound manifest
and completed hash-checking audit are at
`out/integrated-final-qbs-akv-pairs-20260925-01/paired_manifest_rebound.json`
and `audit_rebound_archived.json`. The new independent audit reports PASS for
all 10 QBS/RVV pairs plus the AKV/RVV pair, with matching VCS image identity,
no missing QBS format, and zero issues. It records the historical runner SHA-256
`c0a514ea7875439053367720824117b045b706947150140dfd8250ac4d549310`.
The original FAIL audit remains unchanged; the rebound PASS makes these frozen
programs eligible as *candidates* for later same-image coverage replay, but
does not itself contribute to a Verilator coverage percentage.
The Q4_K prefill, Q8_0, and AKV-v2 frozen ELFs each pass the current 2 MiB,
16-byte-aligned Verilator RAM fit check. They are a bounded stage-2 shortlist,
not scheduled runs; select among them only after the stage-1 uncovered-point
review identifies a relevant QBS/AKV gap.
`coverage/paired_stage2_candidates_20260925.json` records this three-case
shortlist. Its runner first verifies the frozen source hashes and re-audits
the paired programs with the archived runner; no stage-2 replay has started.
For reproducibility, `frozen_sources/` under the paired-run directory holds
90 copied source files (7.1 MiB), including the captured tensors and the
historical runner, plus a re-bound paired manifest. Its local hash check
passes; `frozen_sources/audit.json` independently reports PASS for all 10
QBS/RVV pairs and the AKV/RVV pair, with matching image identity and no
issues. The
source snapshot does not duplicate the separate frozen VCS image and run logs.
