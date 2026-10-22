# Full192 Readiness And Four-Point Budget Review

Preparation only. **No full192 DUT authorization or launch.** This successor
note updates calibration without editing README/VCS_PLAN/reference sources or
the plan pinned by the running software-reference campaign.

## Acceptance And Reference Readiness

Selected4 candidate04 now independently accepted: see
[DUT_ACCEPTANCE.md](../sv39/DUT_ACCEPTANCE.md). All four complete CSVs,
12394 comparisons, precise traps/retry, allowed partial fields, whole-memory,
guard/CSR/restore/magic and executed image/ELF pins passed. That is not full192
or original169/128 closure.

Full192 geometry was independently re-audited: exactly trial0..191 in48
groups4g..4g+3, with72 permission-fault cases,72 unmapped-fault cases and48
alloff cases. No omitted or duplicated trial across accepted group0 and the
two remaining reference partitions. Each uses unchanged archived target S,
original formulas/setup/restart and the strict source-derived whole-memory
oracle; negative checks retain each trial's partial-field allowances.

All192 host formulas passed909504 rows. Group0/trials0..3 passed real Spike
with12370 checks/1001948 retiring commits. Remaining references were launched
under `ara-nf8-full192-spike-01.service`, two workers,90s per Spike process,
7200s outer, stop-first-failure. The one completion-path check in this review
found no `reference_campaign01/complete.json`. No new partial-group progress
query was made; therefore **full192 reference readiness is not yet asserted**.
Existing [startup evidence](reference_campaign01/startup_observation.json)
records two real reference traces advancing, not aggregate PASS.

Required before a DUT admission proposal is executable: terminal exact192
reference/negative PASS; independently audited complete group membership and
all accepted ELF hashes; full-group CSV/ledger adapter and host negatives;
parent-reviewed image, source/config pins and fixed budgets; fresh resource
admission including other work's reservations. None of these gates is bypassed
by the four representative DUT passes or by this budget document.

## Four-Point Timing

| Trial | Type | Measured seconds | Last cycle |
| --- | --- | ---: | ---: |
| 19 | load fault/retry, stride44 | 470.1075 | 374954 |
| 17 | load fault/retry, stride36 | 442.9078 | 374876 |
| 67 | store fault/retry, stride44 | 432.2455 | 374784 |
| 31 | alloff load | 322.4095 | 277218 |

Grouping keeps original mode fixed within four gap/split tuples:36 fault
groups and12 alloff groups. Without claiming a shared-initialization DUT
speedup, using the maximum measured fault cost gives about1880.43s per fault
group and the one measured alloff cost gives1289.64s per alloff group. The
weighted48-group workload is about83171s, or5.78h at four workers. This is a
projection, not a bound: MAPERR refill, alloff store, other boundaries/masks,
grouped binaries and concurrent machine load are not measured by these four.

Retain the conservative proposal:2400s per group,2700s orchestration including
teardown/checker; jobs4 gives12 waves and33600s outer (9h20m). If parent selects
jobs2, use24 waves with a separately pinned66000s outer, not the jobs4 limit.
No automatic timeout increase or rerun. This proposal does not launch anything.

## Resource Snapshot, Not Admission

One read-only resource snapshot at Unix1791714035.683 observed two live simv
processes and196891496448 bytes MemAvailable (about183.4GiB). No service/group
progress was queried or external process changed. No Spike happened to be
live at that instant; the two reference-worker reservations remain budgeted
until their terminal state is accepted.

For planning, observed2 + reference reserve2 + proposed DUT4 =8 of24 slots,
before any additional parent-declared reservations. This is **not a launch
admission** or a promise that resources remain free. A future launch must
recheck total live/reserved <=24 and MemAvailable>=32GiB once, bind all current
reservations, and refuse saturation without polling. NF7 and other-session
work remain untouched. Await parent review and explicit full192 DUT permission.

Original Linux/SIG equivalence limits remain unchanged: these tests do not
execute the Linux ELF, inspect signal-frame ABI, or prove the aggregate169/128
failure's cause or Linux context handling repaired.
