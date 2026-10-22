# M4 FP3 Plan: Not Authorized

Plan SHA256: `f503af9bfac573987090e3ac1eea08f10f8e7768e390c757ea4e5095769caed6`.
Exact existing three SoC ELFs/oracles; jobs2; 2726 pins unchanged; M4 image and
453 compiled-source manifest entries checked. No build, software rebuild, DUT
launch or active-task polling. The preparation tool has no launch entry point.

## Mandatory Scheduling Gates

1. Parent38 must PASS and release its service/workers/slots.
2. Gather75 must reach a terminal result and release its workers. Initial
   admission is insufficient: its per-case checks retain the old38four reserve.
3. NF8 must complete its first admission.
4. Parent must explicitly approve this exact plan and long budget, confirm
   reservation accounting, and provide admission/terminal evidence paths.
5. Startup and every later dispatch must respect cap24, MemAvailable32GiB,
   other reservations, and the FP2 allocation. No automatic retry for capacity.

After these gates the stated other reservations are whole6+NF7two+NF8eight+
prefix5two=18, plus FPtwo=20. This is a scheduling reservation, not a measurement
of currently free slots. Prior drafts01/02 are retained, superseded and unlaunched.

## Measured Budget

New Spike debug commands measure `minstret` at `_start` and `replay_exit` using
the same pinned reference ELFs; all original oracles still pass. Logs and
completed-run CSV calibration are in `../budget01/`, not the live38 directory.

| Exact case | Spike retired | Nominal at500 retire/s | Proposed inner bound |
| --- | ---: | ---: | ---: |
| alias_v8_e16m8_prefix682 | 20,260,288 | 40,521s / 11.26h | 61,200s / 17h |
| restart_e16m2_prefix130 | 1,155,845 | 2,312s | 3,600s |
| restart_unmasked_e16m2_prefix130 | 1,155,294 | 2,311s | 3,600s |

Formula: round up `1.5 * retired / 500 + 120` to300s. Completed M2 FP matrices
measure600-679 retire/s; the completed M4 scalar-restart control measures484/s.
M4 restart_compare measures331/s, demonstrating shape sensitivity. At330/s the
682-call nominal time is61,395s, already exceeding its proposed inner bound.
Consequently these bounds require explicit review, not automatic launch or a
claim that17h is guaranteed sufficient. The682-call program is unsuitable for
a minutes-scale smoke. No oracle/call filtering was introduced to reduce it.

Sum inner budgets68,400s; jobs2 with682-call first gives a budgeted makespan
61,200s. Proposed outer service64,800s leaves3,600s beyond that makespan.
The raw budget01 calculation using the tiny slide control's109 retire/s is
retained but rejected as a representative FP throughput estimate; no DUT
timeout has been changed or used in this preparation.

## Strict Checks

`../prepare_m4_plan.py` includes the checker and27 passing host checks. Require
exactly one original PASS summary with the exact call count and errors0, exact
case/global PASS markers, process return0, tohost0 SUCCESS and `$finish`.
Raw FP DETAIL/FAIL, other RVV FAIL, MATRIX/EXTENSION_MATRIX/EXTENDED/EPOCH FAIL,
trap, assertion/fatal and SKIP indications veto PASS. Missing logs or checker
exceptions cancel peers and queued work; first failure stops the batch.

Full CSV audit requires monotonic cycles, contiguous retired order, no trap,
and exact per-PC/opcode target retirement multiplicities from each original
ordered call sequence. Store actual retirement counts, cycles and walltime;
Spike counts are sizing evidence, not required bit-identical SoC counts.
The future launch integration must apply this checker through the existing
frozen runner and recheck all pins before/after; it is not launched here.
