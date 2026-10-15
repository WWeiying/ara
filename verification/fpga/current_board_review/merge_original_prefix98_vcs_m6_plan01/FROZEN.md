# Prepared Handoff, Not Launch Authorization

Only this new directory was changed. No DUT, build, reference rerun, FSDB or
live-simulation query was performed. Shared helpers, accepted producer inputs
and independent-review artifacts remain immutable.

## Final Identities

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json | f97d3e2a933bfde527b1dd06b54f0055cb1bc2fca103d97308b1d0d45104b079 |
| prepared01/ready.json | fdeddeed08383bb993f28599f1141f860ba48aaf1fa07bf4b614c0ddd0f58149 |
| checker.py | 68ea8fac710500f9dda01606b4c633d91d09fdf1c75d6db766e316b7dfd01683 |
| replay.py | fba6b7d84d530d0b7a40e2ac25ae99231970a610aeeb34020cfc9dd2a13b7942 |
| test_host.py | 20680cfba425c953157ea26befa6790f02e7e571a96dba1696d3a25e12b3085b |
| host02.json | 5bb5e6e8b6ace30bbf29676f158c4678a9403e463c15efd61564dad0972c26bc |

Plan binds725 source/reference/auditor/checker/helper/image pins. Exact accepted
source/reference admission e4b71f9c... and REVIEW7790c949... are included, not
assumed from a pending draft. Original ELF and98-call scope are unchanged.

Host02: **13 test methods PASS,67.457s**, including24 discriminatory trace
negative subcases, a complete98 synthetic positive through both strict and
frozen generic CSV gates, and the actual partial-DETAIL child-process monitor.
The fixture/metadata/resource/abort tests are Host evidence, not DUT results.
Host01 remains a preserved failure caused by missing legal vector-CSR CVX
events in its synthetic fixture; README explains the narrow correction.

Actual existing frozen-runner dry-run completed:
`prepared01/dryrun_check.json`: PASS_DRYRUN_NO_SIMULATOR;
`prepared01/dryrun/run.json`: DRY_RUN, one exact case, no build;
the printed command uses M6simv,seed1,original SoCELF,+NO_FSDB,+COMMIT_TRACE.
Dry-run deliberately prints the source ELF; an authorized real run uses the
runner's private input.elf and validates its provenance/hash/command. No
private DUT execution or actual simv process is claimed by dry-run.

## Gates Still Required

The future direct service command is fully emitted in prepared01/ready.json.
It has two deliberately unresolved values: PARENT_REVIEW_JSON and
PARENT_REVIEW_SHA256. No valid parent launch approval was created here.
Independent runner review and explicit parent authorization must precede
launch. The worker then verifies its direct service owner/cgroup/bus,
10200-second outer limit, exact9000-second case, no retry/build/FSDB,
live-plus-unused-reservation cap24 and available memory32GiB.

No live resource availability was polled or certified. reserved_slots=0
means no additional unused reservation; actual external simv processes are
counted at authorized runtime. This is not a claim that zero other jobs exist.

Result scope if later passed is original natural98/full50176+196 only, with
all97 predecessors. Unknown historical stopped tuple, full2688 child, Linux
replay, parent matrices and the other integer-merge records remain separate.
