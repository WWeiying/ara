# Two Authentic Gather Child Prefixes: Launch Plan Only

No new DUT authorization is implied. Nothing is launched by preparation,
host tests or integration dry-run. All new artifacts stay in this directory;
the accepted83, old TIMEOUTs, preparation03 and frozen M4 remain unchanged.

## Exact Scope And Provenance

Only `gather_prefix_e8_m4_ops1` (masked vx) and
`gather_prefix_e8_m4_ops20` (masked indexed-e16), each original first98 calls.
The endpoint is original ordinal98: `(seed,op,s,l,mode,trial)` =
`(0,1 or20,0,6,0,1)`, VL512, vstart256, scalar0, all-on predicate.
66 is an e8m8 boundary and is rejected here. No arbitrary reduced stimulus,
empty-loop narrowing, rebuilding or additional14-case/parent batch occurs.
Previous97 actual same-child calls and original excluded-op empty iterations,
RNG/setup, full512-element scalar oracle, both guards and all13 original asm
instructions are retained in immutable `../stall_prefix2_03/` inputs.

Authentic C source:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`
SHA256 `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
Archived child ELFs originate in `rvv_permute_partitions01/release/binaries/`
as `rvv_permute_restart_e8_m4_ops1` and `rvv_permute_restart_e8_m4_ops20`.
Their exact original hashes and aliases, source diffs, host negatives,
Spike raw retirement and ELF routine proof are pinned in the reused preparation.

Archived compiler: Buildroot GCC14.3.0; port compiler: existing Xuantie
GCC14.1.1. Whole Linux ELF rebuild is NOT byte-identical. Original C identity
is manifest-backed and all13 target routine encodings match old ELF/SoC ELF.
These are source ports, NOT original Linux ELF execution. The archived
stopped tuple remains UNKNOWN; passing either prefix does not reproduce or
close any exact11 archived failure or full-parent predecessor history.

Spike retired-to-exit costs: 2,148,472 /2,280,966. These are architectural
retirements, not DUT cycles. Reviewed runtime estimate1-2h is not guaranteed.
The new bound is9000s per case, jobs2, outer9600s (plus systemd120s stop grace),
no retries. Existing M4 image is reused, never rebuilt:
`/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`.

## Strict Acceptance

Requires runner exit0, exact COMPLETE/PASS2, no abort, unchanged pins and
private ELF/image/argv/cgroup identities. Both raw consoles must contain
exact98-call/fulloracle PASS statistics and generic successful exit, with
FAIL/DETAIL/TRAP/SKIP/ABORT/parent-PASS veto even after a PASS marker.
The frozen CVX/retirement/backend trace validator is reused unchanged.
Independent CSV counts must agree with its total rows/last cycle/retire count.
Each call must execute the exact13 original instructions in order, correct
input/index/output/predicate pointers, cap512, original VL/vstart/scalar and
zero returned vstart. Each call separately requires512 scalar output reads
and two guards (98 totals:50,176+196=50,372), matching the independent original
tuple model; an address union across calls cannot pass. Actual SoC CTRL store
at0xd0000000 must carry raw returncode0 at the ELF's original replay_exit store
PC (unlike Spike HTIF's encoded1); both value1 and nonzero returncodes reject.
Full RNG/array/predicate initialization
semantics are source-pinned and checked by existing host+Spike evidence;
the DUT checker additionally verifies original vector-load sequence and
call arguments, rather than claiming vector register contents from RVFI.

Failure/timeout/identity error stops only this service's own stage; no retry
and no edits. Its first60s monitor captures two real simv PIDs, generation,
CPU/CSV bytes/last complete cycle growth and raw samples, then stops sampling.
First no-growth sample or process-exit race does not bypass the60s window;
fatal identity mismatch rejects immediately. There is no terminal polling.

## Slot Transfer, Not Queueing

FP1302 is now terminal and independently accepted: `TERMINAL08.md` and
`candidate04_restart_run04/complete.json` are pinned from fp_comparison_original;
terminal SHA256 `ef2eb50bdf0e4f4eb35e9af794d2fdf26cca99286623723818507265ab650747`.
The dependency is `ara-fp-original-restart-candidate04-02.service` (FP1302),
output `current_board_review/fp_comparison_original/candidate04_restart_run04/`.
The WAIT-until-terminal rule remains encoded, but no additional wait or
service polling is needed now. Parent must explicitly coordinate and
bind the final FP complete.json hash and reviewed ready SHA. A terminal FP
failure releases scheduling only, never becomes a Gather PASS claim.
Fresh admission requires structured service terminal state and zero PIDs,
plus all-process/cgroup absence. Unreadable/bus/query errors reject.
FP2 slots are REPLACED with Gather2, not added: whole6+NF7two+NF8eight+
prefix5two+Gather2=20 reserved; unknown simv are additionally charged, cap24
and available memory>=32GiB. Potential unreadable simv reject; Tesla conflicts
reject. Each case rechecks resources. No queue loop or automatic FP wait.
The audit independently observed collected/inactive state and no owned
process/cgroup. Parent separately reported a pre-GC successful service exit;
do not fabricate recovered journal or post-GC numeric service-exit evidence.

Preseal host iteration initially rejected use of a nonexistent SoC `tohost`
symbol, then the strict-window regression detected a final extra0.5s wait.
Both are fixed in this new directory before sealing; no DUT was run for
either failure. Preparation requires all17 host tests PASS, including delayed
growth, PID exit/re-discovery, full60s no-growth cancellation and identity veto.

## Review And Future Commands

Entrypoint: `replay.py`; raw independent checker: `checker.py`;
host regression: `python3 -B test_plan.py` (prints only, no evidence overwrite).
Review `plan.json`, `host_gate.json`, `dryrun_gate.json`, `review_ready.json`
and `review.template.json`. Preparation/dry-run are single-use.

Only after separate parent review/authorization, explicit finished FP evidence
and coordinated slot transfer, the parent may invoke this command with exact
reviewed hashes (NOT executed during this task):

```bash
python3 -B replay.py launch --authorize-run \
  --review /absolute/path/to/new/parent_review.json \
  --review-sha256 APPROVED_PARENT_REVIEW_SHA256 \
  --ready-sha256 REVIEW_READY_SHA256
```

Future unit: `ara-gather-prefix2-candidate04-01.service`, directly owns worker,
KillMode=control-group, Restart=no, RuntimeMaxSec=9600. Future output only:
`stall_prefix2_launch01/vcs_candidate04_01/`; raw logs under
`replay/tests/<name>/{console.log,work/run.vcs.log,commit_trace.csv}`;
startup evidence `actual_simv_confirmation.json`; terminal `complete.json`.
This output is not created until explicit authorized launch admission passes.
