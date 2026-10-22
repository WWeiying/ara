# M6 Regression48 Independent Terminal Audit

Verdict: **M6_EXACT48_DUT_CASES_ACCEPTED_16_FULL_CSV_BYTE_IDENTICAL**.
No DUT/Host rerun, sealed edit, process/service query, or live e8 observation.
The accepted functional scope is the exact frozen48-program plan. Performance
conclusion is limited to the16 identical normal control programs/config/seed.

## Exact Functional Scope

The inventory and sealed plan independently select38 original programs/jobs4,
then10 smokes/jobs2:48 unique members and48 distinct ELF hashes. The six singles
used as controls are already in the38, not additional cases. Complete status
is PASS_48_ARCHITECTURAL, aborted=false, pins_unchanged=true; both stages are
COMPLETE/PASS38 and COMPLETE/PASS10 with exact membership and summaries.

All48 have actual numeric returncode0 and elapsed within unchanged case budgets.
All48 private ELFs, original source/input provenance, actual image and command,
seed1/default/no-FSDB/trace settings, both raw logs and original full oracle/
failure-veto/normal simulator exit gates verify. Smoke oracle sequences match
the sealed baseline. Generic trace summaries are VALID and raw traces hash-bound;
this audit does not invent a new numerical oracle for the other32 programs.

All755 plan pins and exact372 terminal evidence pins verify before/after with
original artifacts unchanged. Combined1137 immutable bindings and per-case
members/ELF/rc0/log/trace facts are retained in `audit.json`.

## Full16 Control Comparison

Reused baseline is the pinned M4 comparison_alias_original/candidate04_01
PASS_19_PLUS_16 identity. Baseline/current private ELFs match; actual commands
use the same program, seed1, default configuration and no wave capture.
Actual baseline/current simulator.conf hash is the same6aaa87... below.

Every byte of all16 complete commit_trace.csv files was compared directly,
including cycle, retirement and all noncycle event fields. All are identical:
combined310350 rows/34344881 bytes. Raw control oracle sequences match in both
logs. Recorded performance rows/counts/noncycle equality/zero cycle changes and
header-only differences CSVs independently agree with the actual comparison.

| Control | Complete Rows | Retired | Last Cycle |
| --- | --- | --- | --- |
| rvv_vadd | 40797 | 39347 | 65438 |
| rvv_vslideup | 33635 | 32570 | 56008 |
| rvv_vslidedown | 26447 | 25714 | 41490 |
| rvv_vrgather | 17283 | 16734 | 28256 |
| rvv_vmseq | 43836 | 41817 | 65658 |
| rvv_vfredosum | 32611 | 31544 | 51740 |
| rvv_vfwredosum | 21708 | 20949 | 34438 |
| qbs_control_smoke | 1259 | 1175 | 4383 |
| akv_context_smoke | 14990 | 14780 | 25397 |
| qbs_akv_handoff_smoke | 4685 | 4501 | 11318 |
| maskslide | 11578 | 11521 | 19497 |
| restart_compare | 18975 | 18918 | 30319 |
| reduction_fflags | 5381 | 5324 | 9435 |
| m8widen | 12408 | 12353 | 21158 |
| wholemove | 23161 | 23114 | 33222 |
| slide1up_prestart | 1596 | 1550 | 3046 |

**No observed cycle regression in these16 normal controls**. This is not an
all-workload performance result, host wall-time comparison, or proof about
unmeasured indexed/fault/mixed-layout shapes. Full per-control ELF/CSV identities
and baseline/current paths are retained in `controls16.json`.

## Child Versus Outer Service Exit

Each simulator rc0 is explicitly present in the actual stage/terminal records.
Coordinator child.json records PID675396, parent628354, exact regression command
and shared followup cgroup. Its pinned fresh02 REGRESSION48_PASS record binds
this exact regression terminal SHA and all372 evidence hashes. Reviewed frozen
coordinator code requires child.returncode0 and no cancellation *before* it
accepts/publishes this result. Thus child rc0 is supported by that code/record
path, not by the parent's observation that the child disappeared; a standalone
numeric wait-status JSON is not present and is not invented here.

The parent reported followup service GC/not-found. **Actual outer service exit
facts are unavailable; outer service exit0 is not accepted.** GC/defaultsuccess
and missing PID were not used as positive evidence, and no current OS query was
made. Existing whole3 M6 functional/actual-exit acceptance remains separate.

## Final Identity

Plan: `ac33642809800f58c5f4534bdb52622849335ee3872a2b4347da7b7588ff8929`.
M6 image: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
Config: `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.
Snapshot: `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.
Regression complete: `3b04cfeb7ce99c8f5eb3e5e9a7b042c85e510fce4383eb9b7467bc7f9d175d40`.
Coordinator complete: `5bc1fd9220ffd72e0997df7f28ecd5659232729bf51c24d1966a92d61b09b3e4`.
Baseline image: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

These fixed SoC programs do not establish original Linux schedules/full-parent
closure. No existing acceptance report, root document, helper, image or RTL was
modified; only this new owned audit directory was written.
